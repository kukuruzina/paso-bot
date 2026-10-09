from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command

import httpx

from ..config import load_config
from ..plans import PLANS, get_plan, format_plan_title

router = Router()


# =========================
# КНОПКИ ТАРИФОВ
# =========================
def kb_plans():
    rows = []
    for key, plan in PLANS.items():
        label = plan["title"] + " — €" + plan["price_eur"]
        rows.append([InlineKeyboardButton(text=label, callback_data="plan:" + key)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# =========================
# ЭКРАН ПОДПИСКИ
# =========================
async def render_subscription(message: Message):
    lines = ["💳 Подписка PASO", "", "Выберите тариф:", ""]
    for plan in PLANS.values():
        lines.append(plan["title"] + " — €" + plan["price_eur"] + " (" + plan["benefit"] + ")")
    await message.answer(chr(10).join(lines), reply_markup=kb_plans())


# =========================
# ВЫБОР ТАРИФА
# =========================
@router.callback_query(F.data.startswith("plan:"))
async def select_plan(callback: CallbackQuery):
    plan = callback.data.split(":", 1)[1]
    if get_plan(plan) is None:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return
    text = "💳 Подписка PASO\n\nВы выбрали:\n" + format_plan_title(plan) + "\n\nВыберите способ оплаты:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌍 Оплатить картой (Stripe)", callback_data="pay_stripe:" + plan)],
        [InlineKeyboardButton(text="🇷🇺 Оплатить через YooKassa", callback_data="pay_yk:" + plan)],
    ])
    await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


# =========================
# STRIPE ОПЛАТА
# =========================

@router.callback_query(F.data.startswith("pay_stripe:"))
async def pay_stripe(callback: CallbackQuery):

    plan = callback.data.split(":", 1)[1]
    if get_plan(plan) is None:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return
    cfg = load_config()

    try:

        async with httpx.AsyncClient() as client:

            r = await client.post(
                "http://127.0.0.1:8000/stripe/create_checkout",
                json={
                    "tg_user_id": callback.from_user.id,
                    "plan": plan
                },
                timeout=20,
            )

        print("STRIPE STATUS:", r.status_code)
        print("STRIPE RESPONSE:", r.text)

        if r.status_code != 200:
            raise Exception(f"Stripe status {r.status_code}")

        data = r.json()

        url = data.get("url")

        if not url:
            raise Exception("No checkout url")

    except Exception as e:

        print("STRIPE ERROR:", e)

        await callback.message.answer(
            f"Ошибка Stripe 😢\n\n{e}"
        )

        return

    await callback.message.answer(
        "💳 Перейдите к оплате:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Оплатить",
                        url=url
                    )
                ]
            ]
        )
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
        plan = callback.data.split(":", 1)[1]
        if get_plan(plan) is None:
            await callback.answer("Неизвестный тариф", show_alert=True)
            return

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






