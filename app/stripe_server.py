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
            }
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

    tg_user_id = data.tg_user_id

    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        raise HTTPException(status_code=500, detail="YooKassa not configured")

    url = "https://api.yookassa.ru/v3/payments"

    payload = {
        "amount": {
            "value": "555.00",
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": f"{PUBLIC_BASE_URL}/yookassa/success"
        },
        "capture": True,
        "description": "PASO subscription (30 days)",
        "metadata": {
            "tg_user_id": str(tg_user_id)
        }
    }

    headers = {
        "Idempotence-Key": str(uuid.uuid4())
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)
        )

        data = response.json()

        if "confirmation" not in data:
            raise HTTPException(status_code=500, detail=str(data))

        return {
            "url": data["confirmation"]["confirmation_url"]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========================
# 🔥 WEBHOOKS
# ========================

@app.post("/yookassa/webhook")
async def yookassa_webhook(request: Request):
    data = await request.json()

    print("🔥 YOOKASSA WEBHOOK:", data, flush=True)

    if data.get("event") == "payment.succeeded":
        obj = data.get("object", {})
        metadata = obj.get("metadata", {})
        tg_user_id = metadata.get("tg_user_id")

        if tg_user_id:
            async with get_session() as session:
                await activate_subscription(
                    session,
                    user_id=int(tg_user_id),
                    source="yookassa"
                )

    return {"ok": True}


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    data = await request.json()

    print("🔥 STRIPE WEBHOOK:", data, flush=True)

    if data.get("type") == "checkout.session.completed":
        session_data = data.get("data", {}).get("object", {})
        metadata = session_data.get("metadata", {})
        tg_user_id = metadata.get("tg_user_id")

        if tg_user_id:
            async with get_session() as session:
                await activate_subscription(
                    session,
                    user_id=int(tg_user_id),
                    source="stripe"
                )

    return {"ok": True}


# ========================
# RUN
# ========================

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)


