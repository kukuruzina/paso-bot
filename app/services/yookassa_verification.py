import os
from decimal import Decimal, InvalidOperation

import httpx
from dotenv import load_dotenv

from app.plans import get_plan

load_dotenv(dotenv_path="/root/paso-bot/.env")

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
YOOKASSA_API_URL = "https://" + "api.yookassa.ru" + "/v3/payments"


async def verify_yookassa_payment(payment_id: str) -> dict:
    """Получает платёж напрямую из YooKassa и проверяет его данные."""
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        raise RuntimeError("YooKassa credentials are not configured")

    if not payment_id or len(payment_id) > 128:
        raise ValueError("Invalid YooKassa payment ID")

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"{YOOKASSA_API_URL}/{payment_id}",
            auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
            headers={"Content-Type": "application/json"},
        )

    if response.status_code != 200:
        raise ValueError(
            f"YooKassa payment lookup failed: HTTP {response.status_code}"
        )

    payment = response.json()

    if payment.get("id") != payment_id:
        raise ValueError("YooKassa payment ID mismatch")

    if payment.get("status") != "succeeded" or payment.get("paid") is not True:
        raise ValueError("YooKassa payment is not confirmed as paid")

    metadata = payment.get("metadata") or {}
    tg_user_id = metadata.get("tg_user_id")
    plan_key = metadata.get("plan")

    if not tg_user_id or not str(tg_user_id).isdigit():
        raise ValueError("Missing or invalid Telegram user ID")

    plan = get_plan(plan_key)
    if plan is None:
        raise ValueError("Unknown plan in YooKassa metadata")

    amount = payment.get("amount") or {}
    try:
        actual_minor = int(
            (Decimal(str(amount["value"])) * 100).quantize(Decimal("1"))
        )
        expected_minor = int(
            (Decimal(str(plan["yookassa_amount"])) * 100).quantize(Decimal("1"))
        )
    except (KeyError, InvalidOperation, TypeError, ValueError):
        raise ValueError("Invalid amount in YooKassa payment")

    actual_currency = str(amount.get("currency", "")).upper()
    expected_currency = str(plan["currency"]).upper()

    if actual_minor != expected_minor or actual_currency != expected_currency:
        raise ValueError("YooKassa payment amount or currency mismatch")

    return {
        "payment_id": payment_id,
        "tg_user_id": int(tg_user_id),
        "plan_key": plan_key,
        "amount_minor": actual_minor,
        "currency": actual_currency,
    }
