from __future__ import annotations

import os
from datetime import datetime, timedelta

import stripe
from fastapi import FastAPI, Request, HTTPException
from sqlalchemy import select
from dotenv import load_dotenv

from app.db import get_session
from app.models import User, Subscription

load_dotenv()

# =========================
# CONFIG
# =========================
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8080")

if not STRIPE_SECRET_KEY:
    raise RuntimeError("STRIPE_SECRET_KEY is missing")

stripe.api_key = STRIPE_SECRET_KEY

# =========================
# PRICE CONFIG
# =========================
STRIPE_PRICES = {
    "single": os.getenv("STRIPE_PRICE_SINGLE"),
    "standard": os.getenv("STRIPE_PRICE_STANDARD"),
    "pro": os.getenv("STRIPE_PRICE_PRO"),
    "premium": os.getenv("STRIPE_PRICE_PREMIUM"),
}

# какие тарифы — подписки
SUBSCRIPTION_PLANS = {"pro", "premium"}

# сколько дней давать доступ
PLAN_DAYS = {
    "single": 1,
    "standard": 14,
    "pro": 30,
    "premium": 30,
}

app = FastAPI()


def _now_utc() -> datetime:
    return datetime.utcnow()


# =========================
# АКТИВАЦИЯ ДОСТУПА
# =========================
async def activate_subscription_for_tg_user(tg_user_id: int, plan: str):
    async with get_session() as session:
        res = await session.execute(
            select(User).where(User.tg_user_id == tg_user_id)
        )
        user = res.scalar_one_or_none()

        if not user:
            return

        now = _now_utc()
        days = PLAN_DAYS.get(plan, 30)
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


# =========================
# HEALTH
# =========================
@app.get("/stripe/health")
async def health():
    return {"ok": True}


# =========================
# WEBHOOK
# =========================
@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Webhook secret missing")

    payload = await request.body()
    sig = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig,
            secret=STRIPE_WEBHOOK_SECRET,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event["type"] == "checkout.session.completed":
        session_obj = event["data"]["object"]

        meta = session_obj.get("metadata") or {}
        tg_user_id = meta.get("tg_user_id")
        plan = meta.get("plan")

        if tg_user_id and plan:
            try:
                await activate_subscription_for_tg_user(
                    tg_user_id=int(tg_user_id),
                    plan=plan,
                )
            except Exception:
                pass

    return {"received": True}


# =========================
# CREATE CHECKOUT
# =========================
@app.post("/stripe/create_checkout")
async def create_checkout(payload: dict):
    tg_user_id = int(payload["tg_user_id"])
    plan = payload.get("plan")

    if plan not in STRIPE_PRICES:
        raise HTTPException(status_code=400, detail="Invalid plan")

    price_id = STRIPE_PRICES[plan]

    if not price_id:
        raise HTTPException(status_code=500, detail="Price ID missing")

    # 🔥 КЛЮЧЕВОЕ МЕСТО
    mode = "subscription" if plan in SUBSCRIPTION_PLANS else "payment"

    checkout = stripe.checkout.Session.create(
        mode=mode,
        success_url=f"{PUBLIC_BASE_URL}/stripe/success",
        cancel_url=f"{PUBLIC_BASE_URL}/stripe/cancel",
        line_items=[
            {
                "price": price_id,
                "quantity": 1,
            }
        ],
        metadata={
            "tg_user_id": str(tg_user_id),
            "plan": plan,
        },
    )

    return {"url": checkout.url}


# =========================
# SUCCESS / CANCEL
# =========================
@app.get("/stripe/success")
async def success():
    return {"ok": True}


@app.get("/stripe/cancel")
async def cancel():
    return {"ok": True}

