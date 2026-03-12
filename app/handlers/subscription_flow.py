from __future__ import annotations

import httpx
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..config import load_config

router = Router()


def kb_payments(stripe_url: str | None, yk_url: str | None):
    kb = InlineKeyboardBuilder()

    if stripe_url:
        kb.button(
            text="💳 Оплатить картой (Stripe)",
            url=stripe_url,
        )

    if yk_url:
        kb.button(
            text="🇷🇺 Оплатить через ЮKassa",
            url=yk_url,
        )

    kb.adjust(1)
    return kb.as_markup()


async def render_subscription(message: Message):
    cfg = load_config()

    if not cfg.public_base_url:
        await message.answer("Ошибка: PUBLIC_BASE_URL не настроен.")
        return

    stripe_url: str | None = None
    yk_url: str | None = None

    async with httpx.AsyncClient(timeout=20) as client:

        # Stripe
        try:
            r = await client.post(
                f"{cfg.public_base_url}/stripe/create_checkout",
                json={"tg_user_id": message.from_user.id},
            )

            if r.status_code == 200:
                stripe_url = r.json().get("url")

        except Exception:
            stripe_url = None

        # YooKassa
        try:
            r2 = await client.post(
                f"{cfg.public_base_url}/yookassa/create_payment",
                json={"tg_user_id": message.from_user.id},
            )

            if r2.status_code == 200:
                yk_url = r2.json().get("url")

        except Exception:
            yk_url = None

    if not stripe_url and not yk_url:
        await message.answer("Не удалось создать оплату. Попробуйте позже.")
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
        reply_markup=kb_payments(stripe_url, yk_url),
    )


# команда /subscribe
@router.message(Command("subscribe"))
async def subscribe_cmd(message: Message):
    await render_subscription(message)


# кнопка меню
@router.message(F.text.in_(["💳 Подписка", "Подписка"]))
async def subscribe_menu(message: Message):
    await render_subscription(message)
