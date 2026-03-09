from __future__ import annotations

import uuid
import stripe

from fastapi import FastAPI, HTTPException
from yookassa import Configuration, Payment

from .config import load_config
from .db import init_global_db
from .services.subscriptions import activate_subscription

cfg = load_config()

# init db
init_global_db(cfg.database_url)

# Stripe
stripe.api_key = cfg.stripe_secret_key

# YooKassa
Configuration.account_id = cfg.yookassa_shop_id
Configuration.secret_key = cfg.yookassa_secret_key

app = FastAPI()


@app.get("/")
def root():
    return {"service": "PASO API", "status": "running"}


@app.get("/health")
def health():
    return {"status": "ok"}


# =========================================
# STRIPE CHECKOUT (5 EUR)
# =========================================

@app.post("/stripe/create_checkout")
async def stripe_create_checkout(data: dict):

    tg_user_id = data.get("tg_user_id")

    if not tg_user_id:
        raise HTTPException(status_code=400, detail="tg_user_id required")

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": "eur",
                    "product_data": {
                        "name": "PASO subscription (1 month)",
                    },
                    "unit_amount": 500,  # 5 EUR
                },
                "quantity": 1,
            }
        ],
        metadata={
            "tg_user_id": str(tg_user_id)
        },
        success_url=f"https://t.me/{cfg.bot_username}?start=paid",
        cancel_url=f"https://t.me/{cfg.bot_username}",
    )

    return {"url": session.url}


# =========================================
# YOOKASSA PAYMENT (555 RUB)
# =========================================

@app.post("/yookassa/create_payment")
async def yookassa_create_payment(data: dict):

    tg_user_id = data.get("tg_user_id")

    if not tg_user_id:
        raise HTTPException(status_code=400, detail="tg_user_id required")

    payment = Payment.create(
        {
            "amount": {
                "value": "555.00",
                "currency": "RUB",
            },
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/{cfg.bot_username}?start=paid",
            },
            "description": "Подписка PASO (1 месяц)",
            "metadata": {
                "tg_user_id": str(tg_user_id)
            },
        },
        uuid.uuid4(),
    )

    return {"url": payment.confirmation.confirmation_url}async def health():
    return {"ok": True, "ts": datetime.utcnow().isoformat()}

# yookassa config
if cfg.yookassa_shop_id and cfg.yookassa_secret_key:
    Configuration.account_id = cfg.yookassa_shop_id
    Configuration.secret_key = cfg.yookassa_secret_key
