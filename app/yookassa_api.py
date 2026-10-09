import os
import uuid

import httpx

from app.plans import PLANS


YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")


# Цены тарифов берутся из единой конфигурации PASO.
YOOKASSA_PRICES = {
    key: (plan["yookassa_amount"], plan["currency"])
    for key, plan in PLANS.items()
}


async def create_yookassa_payment(
    tg_user_id: int,
    plan: str = "standard",
) -> str:
    """
    Создаёт платёж YooKassa и возвращает ссылку на оплату.

    Поддерживаемые тарифы: single, standard, pro, premium.
    """

    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        raise Exception("YooKassa credentials not set")

    if plan not in YOOKASSA_PRICES:
        raise Exception(f"Invalid plan: {plan}")

    amount_value, currency = YOOKASSA_PRICES[plan]

    url = "https://api.yookassa.ru/v3/payments"

    headers = {
        "Idempotence-Key": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }

    payload = {
        "amount": {
            "value": amount_value,
            "currency": currency,
        },
        "confirmation": {
            "type": "redirect",
            "return_url": "https://t.me/paso_go_bot",
        },
        "capture": True,
        "description": f"PASO {plan} | user {tg_user_id}",
        "metadata": {
            "tg_user_id": str(tg_user_id),
            "plan": plan,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                url,
                json=payload,
                headers=headers,
                auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
            )
    except Exception as exc:
        print(f"[YOOKASSA ERROR] Request failed: {exc}")
        raise Exception("YooKassa request failed") from exc

    if response.status_code not in (200, 201):
        print(
            f"[YOOKASSA ERROR] HTTP {response.status_code}: "
            f"{response.text}"
        )
        raise Exception(
            f"YooKassa error: HTTP {response.status_code}"
        )

    data = response.json()
    payment_id = data.get("id")
    confirmation_url = data.get("confirmation", {}).get(
        "confirmation_url"
    )

    if not confirmation_url:
        print(
            "[YOOKASSA ERROR] No confirmation URL. "
            f"Payment ID: {payment_id}"
        )
        raise Exception("No confirmation URL in YooKassa response")

    print(
        f"[YOOKASSA] Payment created: {payment_id} "
        f"| plan={plan} | user={tg_user_id}"
    )

    return confirmation_url

