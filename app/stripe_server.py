from __future__ import annotations

import os
import uuid
import stripe
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from dotenv import load_dotenv
import requests

from app.services.subscriptions import activate_subscription
from app.db import get_session

load_dotenv()

app = FastAPI()

# ========================
# CONFIG
# ========================

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL")

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")

stripe.api_key = STRIPE_SECRET_KEY


# ========================
# MODELS
# ========================

class CheckoutRequest(BaseModel):
    tg_user_id: int
    plan: str


# ========================
# STRIPE
# ========================

STRIPE_PRICES = {
    "single": os.getenv("STRIPE_PRICE_SINGLE"),
    "standard": os.getenv("STRIPE_PRICE_STANDARD"),
    "pro": os.getenv("STRIPE_PRICE_PRO"),
    "premium": os.getenv("STRIPE_PRICE_PREMIUM"),
}


@app.post("/stripe/create_checkout")
async def stripe_create_checkout(data: CheckoutRequest):

    tg_user_id = data.tg_user_id
    plan = data.plan

    SUBSCRIPTION_PLANS = ["pro", "premium"]

    mode = (
        "subscription"
        if plan in SUBSCRIPTION_PLANS
        else "payment"
    )

    try:

        if plan not in STRIPE_PRICES:
            raise HTTPException(
                status_code=400,
                detail="Invalid plan"
            )

        price_id = STRIPE_PRICES[plan]

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],

            mode=mode,

            line_items=[
                {
                    "price": price_id,
                    "quantity": 1,
                }
            ],

            success_url=f"{PUBLIC_BASE_URL}/stripe/success",
            cancel_url=f"{PUBLIC_BASE_URL}/stripe/cancel",

            metadata={
                "tg_user_id": str(tg_user_id),
                "plan": plan,
            },
            **(
                {
                    "subscription_data": {
                        "metadata": {
                            "tg_user_id": str(tg_user_id),
                            "plan": plan,
                        }
                    }
                }
                if mode == "subscription"
                else {}
            )
        )

        return {"url": session.url}

    except Exception as e:

        print("STRIPE ERROR:", e)

        import traceback
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# ========================
# YOOKASSA
# ========================

@app.post("/yookassa/create_payment")
async def yookassa_create_payment(data: CheckoutRequest):
    from app.plans import get_plan
    from app.yookassa_api import create_yookassa_payment

    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        raise HTTPException(status_code=500, detail="YooKassa not configured")

    plan_key = data.plan
    if get_plan(plan_key) is None:
        raise HTTPException(status_code=400, detail="Invalid plan")

    try:
        confirmation_url = await create_yookassa_payment(
            tg_user_id=data.tg_user_id,
            plan=plan_key,
        )
        return {"url": confirmation_url}
    except Exception:
        print("YOOKASSA CREATE PAYMENT ERROR", flush=True)
        raise HTTPException(status_code=502, detail="Could not create payment")


@app.post("/yookassa/webhook")
async def yookassa_webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if data.get("event") != "payment.succeeded":
        return {"ok": True}

    obj = data.get("object") or {}
    payment_id = obj.get("id")
    if not payment_id:
        raise HTTPException(status_code=400, detail="Missing payment ID")

    from app.services.yookassa_verification import verify_yookassa_payment
    from app.services.payment_fulfillment import fulfill_payment

    try:
        verified = await verify_yookassa_payment(str(payment_id))
        async with get_session() as session:
            applied = await fulfill_payment(
                session,
                provider="yookassa",
                external_id=verified["payment_id"],
                tg_user_id=verified["tg_user_id"],
                plan_key=verified["plan_key"],
                amount_minor=verified["amount_minor"],
                currency=verified["currency"],
            )
    except ValueError as exc:
        print("YOOKASSA WEBHOOK validation error:", str(exc), flush=True)
        raise HTTPException(status_code=400, detail="Payment validation failed")
    except Exception:
        print("YOOKASSA WEBHOOK processing error", flush=True)
        raise HTTPException(status_code=500, detail="Payment processing failed")

    print(
        "YOOKASSA WEBHOOK processed:",
        verified["payment_id"],
        "new_fulfillment=" + str(applied),
        flush=True,
    )
    return {"ok": True}


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    if not STRIPE_WEBHOOK_SECRET:
        print("STRIPE WEBHOOK ERROR: signing secret is not configured", flush=True)
        raise HTTPException(status_code=500, detail="Webhook is not configured")

    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    if not signature:
        raise HTTPException(status_code=400, detail="Missing Stripe signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, signature, STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook signature")

    event_type = event.get("type")
    obj = event.get("data", {}).get("object", {})

    # Do not fulfill the same payment through payment_intent.succeeded.
    if event_type not in {"checkout.session.completed", "invoice.paid"}:
        return {"ok": True}

    from app.services.payment_fulfillment import fulfill_payment
    from app.plans import get_plan

    try:
        if event_type == "checkout.session.completed":
            session_id = obj.get("id")
            if not session_id:
                raise ValueError("Missing Checkout Session ID")

            checkout = stripe.checkout.Session.retrieve(
                session_id,
                expand=["line_items.data.price"],
            )

            if checkout.get("payment_status") != "paid":
                return {"ok": True}

            if checkout.get("mode") != "payment":
                # Subscription Checkout is fulfilled by invoice.paid.
                return {"ok": True}

            metadata = checkout.get("metadata") or {}
            tg_user_id = metadata.get("tg_user_id")
            plan_key = metadata.get("plan")
            plan = get_plan(plan_key)

            if not tg_user_id or plan is None:
                raise ValueError("Missing or invalid Checkout metadata")

            try:
                tg_user_id = int(tg_user_id)
            except (TypeError, ValueError):
                raise ValueError("Invalid Telegram user ID")

            expected_price_id = STRIPE_PRICES.get(plan_key)
            line_items = checkout.get("line_items", {}).get("data", [])
            if len(line_items) != 1:
                raise ValueError("Unexpected Checkout line item count")

            item = line_items[0]
            price = item.get("price")
            price_id = price.get("id") if price else None
            if price_id != expected_price_id or item.get("quantity") != 1:
                raise ValueError("Checkout price or quantity mismatch")

            price = stripe.Price.retrieve(price_id)
            amount_minor = checkout.get("amount_total")
            currency = (checkout.get("currency") or "").upper()

            if (
                not amount_minor
                or amount_minor != price.get("unit_amount")
                or currency != (price.get("currency") or "").upper()
                or not price.get("active")
                or currency != "EUR"
            ):
                raise ValueError("Checkout amount or currency mismatch")

            async with get_session() as db_session:
                applied = await fulfill_payment(
                    db_session,
                    provider="stripe",
                    external_id=session_id,
                    tg_user_id=tg_user_id,
                    plan_key=plan_key,
                    amount_minor=amount_minor,
                    currency=currency,
                )

            print(
                "STRIPE CHECKOUT processed:",
                session_id,
                "new_fulfillment=" + str(applied),
                flush=True,
            )
            return {"ok": True}

        # invoice.paid: initial subscription payment and renewals.
        invoice_id = obj.get("id")
        if not invoice_id:
            raise ValueError("Missing invoice ID")

        invoice = stripe.Invoice.retrieve(invoice_id)
        if invoice.get("status") != "paid" or invoice.get("paid") is not True:
            return {"ok": True}

        subscription_id = invoice.get("subscription")
        if not subscription_id:
            parent = invoice.get("parent") or {}
            details = parent.get("subscription_details") or {}
            subscription_id = details.get("subscription")

        if not subscription_id:
            # Not a subscription invoice.
            return {"ok": True}

        subscription = stripe.Subscription.retrieve(
            subscription_id,
            expand=["items.data.price"],
        )
        metadata = subscription.get("metadata") or {}
        tg_user_id = metadata.get("tg_user_id")
        plan_key = metadata.get("plan")
        plan = get_plan(plan_key)

        if not tg_user_id or plan is None:
            raise ValueError("Missing or invalid subscription metadata")

        try:
            tg_user_id = int(tg_user_id)
        except (TypeError, ValueError):
            raise ValueError("Invalid Telegram user ID")

        expected_price_id = STRIPE_PRICES.get(plan_key)
        items = subscription.get("items", {}).get("data", [])
        if len(items) != 1:
            raise ValueError("Unexpected subscription item count")

        price = items[0].get("price")
        if not price or price.get("id") != expected_price_id:
            raise ValueError("Subscription price mismatch")

        amount_minor = invoice.get("amount_paid")
        currency = (invoice.get("currency") or "").upper()
        price_amount = price.get("unit_amount")
        price_currency = (price.get("currency") or "").upper()

        if (
            not amount_minor
            or amount_minor != price_amount
            or currency != price_currency
            or currency != "EUR"
            or not price.get("recurring")
        ):
            raise ValueError("Invoice amount or currency mismatch")

        async with get_session() as db_session:
            applied = await fulfill_payment(
                db_session,
                provider="stripe",
                external_id=invoice_id,
                tg_user_id=tg_user_id,
                plan_key=plan_key,
                amount_minor=amount_minor,
                currency=currency,
            )

        print(
            "STRIPE INVOICE processed:",
            invoice_id,
            "new_fulfillment=" + str(applied),
            flush=True,
        )
        return {"ok": True}

    except ValueError as exc:
        print("STRIPE WEBHOOK validation error:", str(exc), flush=True)
        raise HTTPException(status_code=400, detail="Payment validation failed")
    except HTTPException:
        raise
    except Exception:
        print("STRIPE WEBHOOK processing error", flush=True)
        raise HTTPException(status_code=500, detail="Payment processing failed")


# ========================
# RUN
# ========================

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)


