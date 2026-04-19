from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command

import httpx

from ..config import load_config

router = Router()


# =========================
# КНОПКИ ТАРИФОВ
# =========================
def kb_plans():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🥉 Single — €2", callback_data="plan:single")],
        [InlineKeyboardButton(text="🥈 Standard — €5.55", callback_data="plan:standard")],
        [InlineKeyboardButton(text="🥇 Pro — €9", callback_data="plan:pro")],
        [InlineKeyboardButton(text="💎 Premium — €14.5", callback_data="plan:premium")],
    ])


# =========================
# ЭКРАН ПОДПИСКИ
# =========================
async def render_subscription(message: Message):
    await message.answer(
        "💳 Подписка PASO\n\n"
        "Выберите тариф:\n\n"
        "🥉 Single — €2 (1 контакт)\n"
        "🥈 Standard — €5.55 (14 дней доступа)\n"
        "🥇 Pro — €9 (30 дней доступа)\n"
        "💎 Premium — €14.5 (30 дней + приоритет)\n",
        reply_markup=kb_plans(),
    )


# =========================
# ВЫБОР ТАРИФА
# =========================
@router.callback_query(F.data.startswith("plan:"))
async def select_plan(callback: CallbackQuery):
    plan = callback.data.split(":")[1]

    plan_titles = {
        "single": "🥉 Single — €2 (1 контакт)",
        "standard": "🥈 Standard — €5.55 (14 дней доступа)",
        "pro": "🥇 Pro — €9 (30 дней доступа)",
        "premium": "💎 Premium — €14.5 (30 дней + приоритет)",
    }

    text = (
        "💳 Подписка PASO\n\n"
        f"Вы выбрали:\n{plan_titles.get(plan)}\n\n"
        "Выберите способ оплаты:"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🌍 Оплатить картой (Stripe)",
            callback_data=f"pay_stripe:{plan}"
        )],
        [InlineKeyboardButton(
            text="🇷🇺 Оплатить через YooKassa",
            callback_data=f"pay_yk:{plan}"
        )],
    ])

    await callback.message.answer(text, reply_markup=kb)


# =========================
# STRIPE ОПЛАТА
# =========================
@router.callback_query(F.data.startswith("pay_stripe:"))
async def pay_stripe(callback: CallbackQuery):
    plan = callback.data.split(":")[1]
    cfg = load_config()

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{cfg.public_base_url}/stripe/create_checkout",
                json={
                    "tg_user_id": callback.from_user.id,
                    "plan": plan
                },
                timeout=10,
            )

        if r.status_code != 200:
            raise Exception("Stripe error")

        data = r.json()
        url = data.get("url")

        if not url:
            raise Exception("No checkout url")

    except Exception:
        await callback.message.answer("Ошибка оплаты 😢")
        return

    await callback.message.answer(
        "💳 Перейдите к оплате:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить", url=url)]
        ])
    )


# =========================
# YOOKASSA
# =========================
from app.yookassa_api import create_yookassa_payment
from aiogram.utils.keyboard import InlineKeyboardBuilder


@router.callback_query(F.data.startswith("pay_yk:"))
async def pay_yk(callback: CallbackQuery):
    try:
        # извлекаем тариф
        plan = callback.data.split(":")[1]

        # создаём оплату
        url = await create_yookassa_payment(
            tg_user_id=callback.from_user.id,
            plan=plan
        )

        # кнопка оплаты
        kb = InlineKeyboardBuilder()
        kb.button(text="💳 Перейти к оплате", url=url)
        kb.adjust(1)

        await callback.message.answer(
            f"🇷🇺 YooKassa\n\n"
            f"Тариф: {plan}\n\n"
            f"Нажмите кнопку ниже для оплаты 👇",
            reply_markup=kb.as_markup()
        )

    except Exception as e:
        print(f"[YOOKASSA ERROR] {e}")

        await callback.message.answer(
            "❌ Ошибка при создании платежа. Попробуйте позже."
        )

    await callback.answer()


# =========================
# КОМАНДЫ
# =========================
@router.message(Command("subscribe"))
async def subscribe_cmd(message: Message):
    await render_subscription(message)


@router.message(F.text.in_(["💳 Подписка", "Подписка"]))
async def subscribe_menu(message: Message):
    await render_subscription(message)



