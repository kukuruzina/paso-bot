from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

import httpx

from ..config import load_config

router = Router()


def kb_payments(stripe_url: str, yk_url: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Оплатить (карты РФ)", url=yk_url)],
        [InlineKeyboardButton(text="🌍 Оплатить (международные карты)", url=stripe_url)],
    ])


async def render_subscription(message: Message):
    cfg = load_config()

    stripe_url = None

    # === Stripe (обязательно должен работать) ===
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{cfg.public_base_url}/stripe/create_checkout",
                json={"tg_user_id": message.from_user.id},
                timeout=10,
            )
            if r.status_code == 200:
                stripe_url = r.json().get("url")
    except Exception:
        stripe_url = None

    # ❗ если Stripe не работает — показываем ошибку
    if not stripe_url:
        await message.answer("Ошибка оплаты. Попробуйте позже.")
        return

    # === YooKassa (временно заглушка) ===
    yk_url = "https://yookassa.ru/"  # временно для модерации

    await message.answer(
        "💳 <b>Подписка PASO</b>\n\n"
        "Стоимость: <b>555 ₽</b>\n"
        "Срок: <b>30 дней</b>\n\n"
        "Подписка даёт доступ к сервису PASO:\n"
        "— создание заявок на отправку посылок\n"
        "— поиск перевозчиков\n"
        "— отклики на заявки\n"
        "— доступ к контактам пользователей\n\n"
        "🌍 Способы оплаты:\n"
        "🇷🇺 Российские карты — YooKassa\n"
        "🌍 Международные карты — Stripe\n\n"
        "После оплаты подписка активируется автоматически.",
        reply_markup=kb_payments(stripe_url, yk_url),
    )


@router.message(Command("subscribe"))
async def subscribe_cmd(message: Message):
    await render_subscription(message)


@router.message(F.text.in_(["💳 Подписка", "Подписка"]))
async def subscribe_menu(message: Message):
    await render_subscription(message)


