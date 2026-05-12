from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardRemove,
)
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models import User
from ..keyboards import kb_main

from .subscription_flow import render_subscription

router = Router()


# =========================================================
# USER UPSERT
# =========================================================

async def upsert_user(session: AsyncSession, msg: Message):
    tg = msg.from_user

    if not tg:
        return None

    q = select(User).where(User.tg_user_id == tg.id)
    user = (await session.execute(q)).scalar_one_or_none()

    if not user:

        user = User(
            tg_user_id=tg.id,
            tg_username=tg.username,
            first_name=tg.first_name,
            last_name=tg.last_name,
            language_code=tg.language_code,
            contacts_left=5,
        )

        session.add(user)

        await session.commit()
        await session.refresh(user)

    else:

        # 🔄 обновляем username и данные
        user.tg_username = tg.username
        user.first_name = tg.first_name
        user.last_name = tg.last_name
        user.language_code = tg.language_code

        await session.commit()

    return user


# =========================================================
# START
# =========================================================

@router.message(CommandStart())
async def start(
    m: Message,
    state: FSMContext,
    session: AsyncSession,
    command: CommandObject
):
    # 🔥 сброс любого FSM
    await state.clear()

    # 🔥 убрать старые клавиатуры
    await m.answer(
        "⌨️",
        reply_markup=ReplyKeyboardRemove(),
    )

    user = await upsert_user(session, m)

    # =========================================================
    # REFERRAL
    # =========================================================

    if (
        command.args
        and command.args.startswith("ref_")
        and not user.invited_by
    ):
        try:
            inviter_id = int(command.args.split("_")[1])

            if inviter_id != user.id:

                inviter = await session.get(User, inviter_id)

                if inviter:

                    user.invited_by = inviter.id

                    inviter.invites_count = (
                        inviter.invites_count or 0
                    ) + 1

                    inviter.contacts_left = (
                        inviter.contacts_left or 0
                    ) + 1

                    await session.commit()

                    print(
                        f"REFERRAL OK: "
                        f"{inviter.first_name} invited "
                        f"{user.first_name}"
                    )

        except Exception as e:
            print("REFERRAL ERROR:", e)

    # =========================================================
    # AFTER PAYMENT
    # =========================================================

    if command.args and command.args.strip().lower() == "paid":

        await m.answer(
            "✅ Подписка активна!\n\n"
            "Давайте создадим заявку 👇",
            reply_markup=kb_main(is_admin=user.is_admin),
        )

        return

    # =========================================================
    # MAIN START MESSAGE
    # =========================================================

    await m.answer(
        "🚀 Добро пожаловать в PASO бот\n\n"

        "📦 Отправляйте товары через путешественников\n"
        "💸 Или подрабатывайте на доставке\n\n"

        "1️⃣ Создайте заявку или поездку\n"
        "2️⃣ Получите подходящие совпадения\n"
        "3️⃣ Откройте контакт и договоритесь напрямую\n\n"

        "🎁 Новым пользователям +5 контактов бесплатно\n"
        "👥 1 приглашённый друг +1 контакт\n\n"

        "👇 Выберите действие:",

        reply_markup=kb_main(is_admin=user.is_admin),
    )


# =========================================================
# SUBSCRIBE BUTTON
# =========================================================

@router.callback_query(F.data == "go:subscribe")
async def show_subscribe(cq: CallbackQuery):

    await cq.answer()

    await render_subscription(cq.message)


# =========================================================
# REFERRAL MENU
# =========================================================

@router.callback_query(F.data == "ref:menu")
async def referral_menu(cq: CallbackQuery, session: AsyncSession):
    await cq.answer()

    q = select(User).where(User.tg_user_id == cq.from_user.id)
    user = (await session.execute(q)).scalar_one_or_none()

    bot_username = "paso_go_bot"
    ref_link = f"https://t.me/{bot_username}?start=ref_{user.id}"

    text = (
        "🎁 Приглашайте друзей и получайте контакты\n\n"

        "💸 Бонусы:\n"
        "• 1 друг → +1 контакт\n\n"

        f"👥 Вы пригласили: {user.invites_count or 0}\n"

        "🔗 Ваша ссылка:\n\n"
        f"{ref_link}"
    )
    await cq.message.answer(text)


