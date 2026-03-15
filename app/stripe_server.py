from __future__ import annotations

import stripe
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from yookassa import Configuration, Payment
import uuid

from .config import load_config

cfg = load_config()

app = FastAPI()

# ======================
# Stripe
# ======================

stripe.api_key = cfg.stripe_secret_key


class CheckoutRequest(BaseModel):
    tg_user_id: int


@app.post("/stripe/create_checkout")
async def stripe_create_checkout(data: CheckoutRequest):

    tg_user_id = data.tg_user_id

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": "eur",
                        "product_data": {
                            "name": "PASO subscription (30 days)"
                        },
                        "unit_amount": 500,
                    },
                    "quantity": 1,
                }
            ],
            success_url=f"{cfg.public_base_url}/success",
            cancel_url=f"{cfg.public_base_url}/cancel",
            metadata={
                "tg_user_id": str(tg_user_id)
            },
        )

        return {"url": session.url}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ======================
# YooKassa
# ======================

Configuration.account_id = cfg.yookassa_shop_id
Configuration.secret_key = cfg.yookassa_secret_key


@app.post("/yookassa/create_payment")
async def yookassa_create_payment(data: CheckoutRequest):

    tg_user_id = data.tg_user_id

    try:
        payment = Payment.create(
            {
                "amount": {
                    "value": "555.00",
                    "currency": "RUB",
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": f"{cfg.public_base_url}/success",
                },
                "capture": True,
                "description": "PASO subscription (30 days)",
                "metadata": {
                    "tg_user_id": str(tg_user_id)
                },
            },
            uuid.uuid4(),
        )

        return {
            "url": payment.confirmation.confirmation_url
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
