import uuid
import httpx
import os

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")


async def create_yookassa_payment(tg_user_id: int):
    url = "https://api.yookassa.ru/v3/payments"

    headers = {
        "Idempotence-Key": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }

    payload = {
        "amount": {
            "value": "555.00",
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": "https://t.me/paso_go_bot"
        },
        "capture": True,
        "description": f"PASO subscription for user {tg_user_id}",
        "metadata": {
            "tg_user_id": str(tg_user_id)
        }
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json=payload,
            headers=headers,
            auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)
        )

    if response.status_code != 200:
        raise Exception(f"YooKassa error: {response.text}")

    return response.json()["confirmation"]["confirmation_url"]

