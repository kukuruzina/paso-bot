from __future__ import annotations

import httpx
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..config import load_config

router = Router()


def kb_payments(stripe_url: str, yk_url: str | None):
    b = InlineKeyboardBuilder()

    b.button(text="💳 Оплатить картой (Stripe)", url=stripe_url)

    if yk_url:
        b.button(text="🇷🇺 Оплатить через ЮKassa", url=yk_url)

    b.adjust(1)
    return b.as_markup()


async def render_subscription(message: Message):
    cfg = load_config()

    if not cfg.public_base_url:
        await message.answer("Ошибка: PUBLIC_BASE_URL не настроен.")
        return

    try:
        async with httpx.AsyncClient(timeout=20) as client:

            # Stripe checkout
            resp = await client.post(
                f"{cfg.public_base_url}/stripe/create_checkout",
                json={"tg_user_id": message.from_user.id},
            )
            resp.raise_for_status()

            stripe_data = resp.json()
            stripe_url = stripe_data.get("url")

            # YooKassa checkout
            yk_url = None

            try:
                r2 = await client.post(
                    f"{cfg.public_base_url}/yookassa/create_payment",
                    json={"tg_user_id": message.from_user.id},
                )

                if r2.status_code == 200:
                    yk_data = r2.json()
                    yk_url = yk_data.get("url")

            except Exception:
                yk_url = None

    except Exception as e:
        await message.answer(f"Ошибка подключения к оплате: {e}")
        return

    if not stripe_url:
        await message.answer("Не удалось создать оплату (Stripe).")
        return

    await message.answer(
        "💳 Подписка PASO\n\n"
        "Стоимость: 555 ₽ / 30 дней\n\n"
        "Подписка дает доступ к сервису PASO:\n"
        "• создание заявок на отправку посылок\n"
        "• поиск перевозчиков\n"
        "• отклики на заявки\n"
        "• доступ к сообществу перевозчиков\n\n"
        "После оплаты подписка активируется автоматически.",
        reply_markup=kb_payments(
            stripe_url=stripe_url,
            yk_url=yk_url
        ),
    )


# ========================
# Команда /subscribe
# ========================
@router.message(Command("subscribe"))
async def subscribe_cmd(message: Message):
    await render_subscription(message)


# ========================
# Кнопка меню "💳 Подписка"
# ========================
@router.message(F.text.in_(["💳 Подписка", "Подписка"]))
async def subscribe_menu(message: Message):
    await render_subscription(message)
