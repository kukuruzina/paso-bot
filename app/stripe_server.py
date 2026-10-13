from __future__ import annotations

from datetime import datetime, timedelta
import uuid

import stripe
from yookassa import Configuration, Payment
from fastapi import FastAPI, Request, HTTPException
from sqlalchemy import select

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties

from .config import load_config
from .db import init_global_db, get_session
from .models import User

# =========================
# CONFIG
# =========================

cfg = load_config()

init_global_db(cfg.database_url)

stripe.api_key = cfg.stripe_secret_key

Configuration.account_id = cfg.yookassa_shop_id
Configuration.secret_key = cfg.yookassa_secret_key

bot = Bot(
    token=cfg.bot_token,
    default=DefaultBotProperties(parse_mode="HTML"),
)

app = FastAPI()

# =========================
# STRIPE CREATE CHECKOUT
# =========================

@app.post("/stripe/create_checkout")
async def create_checkout(data: dict):
    tg_user_id = data.get("tg_user_id")

    if not tg_user_id:
        raise HTTPException(status_code=400, detail="tg_user_id required")

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "rub",
                "product_data": {"name": "PASO subscription"},
                "unit_amount": 55500,
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url=f"{cfg.public_base_url}/success",
        cancel_url=f"{cfg.public_base_url}/cancel",

        # 🔥 КРИТИЧНО
        metadata={
            "tg_user_id": str(tg_user_id)
        }
    )

    return {"url": session.url}


# =========================
# YOOKASSA CREATE PAYMENT
# =========================

@app.post("/yookassa/create_payment")
async def create_payment(data: dict):
    tg_user_id = data.get("tg_user_id")

    if not tg_user_id:
        raise HTTPException(status_code=400, detail="tg_user_id required")

    payment = Payment.create({
        "amount": {
            "value": "555.00",
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": f"{cfg.public_base_url}/success"
        },
        "capture": True,
        "description": "PASO subscription",
        "metadata": {
            "tg_user_id": str(tg_user_id)
        }
    }, uuid.uuid4())

    return {"url": payment.confirmation.confirmation_url}


# =========================
# STRIPE WEBHOOK
# =========================

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
                user = await session.get(User, int(tg_user_id))
                if user:
                    await activate_subscription(session, user)

    return {"ok": True}


# =========================
# YOOKASSA WEBHOOK
# =========================

@app.post("/yookassa/webhook")
async def yookassa_webhook(request: Request):
    data = await request.json()

    print("🔥 YOOKASSA WEBHOOK:", data, flush=True)

    if data.get("event") != "payment.succeeded":
        obj = data.get("object", {})
        metadata = obj.get("metadata", {})
        tg_user_id = metadata.get("tg_user_id")

        if tg_user_id:
            async with get_session() as session:
                user = await session.get(User, int(tg_user_id))
                if user:
                    await activate_subscription(session, user)

    return {"ok": True}

    async for session in get_session():
        user = await session.get(User, int(tg_user_id))

        if user:
            user.subscription_until = datetime.utcnow() + timedelta(days=30)
            await session.commit()

            await bot.send_message(
                tg_user_id,
                "✅ Подписка активирована (YooKassa)"
            )

    return {"ok": True}


