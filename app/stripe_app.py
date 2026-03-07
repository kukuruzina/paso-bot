from __future__ import annotations

import os
from datetime import datetime, timedelta

import stripe
from fastapi import FastAPI, Request, HTTPException
from sqlalchemy import select

from app.db import get_session, engine  # проверь, что у тебя есть get_session; если нет — скажи, дам адаптацию под твой db.py
from app.models import User, Subscription
from app.config import load_config

cfg = load_config()

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8080")

if not STRIPE_SECRET_KEY:
    raise RuntimeError("STRIPE_SECRET_KEY is missing in .env")

stripe.api_key = STRIPE_SECRET_KEY

app = FastAPI()


def _now_utc() -> datetime:
    return datetime.utcnow()


async def activate_subscription_for_tg_user(tg_user_id: int, days: int = 30) -> None:
    async with get_session() as session:
        res = await session.execute(select(User).where(User.tg_user_id == tg_user_id))
        user = res.scalar_one_or_none()
        if not user:
            # пользователь ещё не нажал /start
            return

        now = _now_utc()
        expires = now + timedelta(days=days)

        sub = Subscription(
            user_id=user.id,
            status="active",
            started_at=now,
            expires_at=expires,
            source="stripe",
            created_at=now,
        )
        session.add(sub)
        await session.commit()


@app.get("/stripe/health")
async def health():
    return {"ok": True}


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="STRIPE_WEBHOOK_SECRET missing")

    payload = await request.body()
    sig = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig,
            secret=STRIPE_WEBHOOK_SECRET,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook error: {e}")

    # Нас интересует только успешная оплата Checkout
    if event["type"] == "checkout.session.completed":
        session_obj = event["data"]["object"]

        # мы положим tg_user_id в metadata при создании checkout
        meta = session_obj.get("metadata") or {}
        tg_user_id = meta.get("tg_user_id")

        if tg_user_id:
            try:
                tg_user_id_int = int(tg_user_id)
                await activate_subscription_for_tg_user(
                    tg_user_id=tg_user_id_int,
                    days=int(os.getenv("SUB_DURATION_DAYS", "30")),
                )
            except Exception:
                # не валим webhook, просто игнорим
                pass

    return {"received": True}


@app.post("/stripe/create_checkout")
async def create_checkout(payload: dict):
    """
    payload: {"tg_user_id": 123}
    """
    tg_user_id = int(payload["tg_user_id"])

    price_eur = int(os.getenv("SUB_PRICE_EUR", "5"))
    success_url = f"{PUBLIC_BASE_URL}/stripe/success"
    cancel_url = f"{PUBLIC_BASE_URL}/stripe/cancel"

    checkout = stripe.checkout.Session.create(
        mode="payment",
        success_url=success_url,
        cancel_url=cancel_url,
        line_items=[
            {
                "price_data": {
                    "currency": "eur",
                    "product_data": {"name": "PASO подписка на 30 дней"},
                    "unit_amount": price_eur * 100,
                },
                "quantity": 1,
            }
        ],
        metadata={"tg_user_id": str(tg_user_id)},
    )

    return {"url": checkout.url}


@app.get("/stripe/success")
async def success():
    return {"ok": True, "message": "Payment success. You can return to Telegram."}


@app.get("/stripe/cancel")
async def cancel():
    return {"ok": True, "message": "Payment canceled. You can return to Telegram."}
