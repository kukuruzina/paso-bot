import uuid
import httpx
import os

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")


# =========================
# ЦЕНЫ (RUB для стабильности)
# =========================
YOOKASSA_PRICES = {
    "single": ("200.00", "RUB"),
    "standard": ("555.00", "RUB"),
    "pro": ("900.00", "RUB"),
    "premium": ("1450.00", "RUB"),
}


# =========================
# СОЗДАНИЕ ПЛАТЕЖА
# =========================
async def create_yookassa_payment(tg_user_id: int, plan: str = "standard"):
    """
    plan:
    - single
    - standard
    - pro
    - premium

    default = standard (чтобы старый код не сломался)
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
    except Exception as e:
        print(f"[YOOKASSA ERROR] Request failed: {e}")
        raise Exception("YooKassa request failed")

    if response.status_code != 200:
        print(f"[YOOKASSA ERROR] {response.text}")
        raise Exception(f"YooKassa error: {response.text}")

    data = response.json()

    payment_id = data.get("id")
    confirmation_url = data.get("confirmation", {}).get("confirmation_url")

    if not confirmation_url:
        print(f"[YOOKASSA ERROR] Invalid response: {data}")
        raise Exception("No confirmation URL in YooKassa response")

    print(f"[YOOKASSA] ✅ Payment created: {payment_id} | plan={plan} | user={tg_user_id}")

    return confirmation_url

