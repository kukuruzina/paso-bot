from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models import User
from ..keyboards import kb_main

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
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return user


# =========================================================
# START
# =========================================================

@router.message(CommandStart())
async def start(m: Message, session: AsyncSession, command: CommandObject):
    user = await upsert_user(session, m)

    # 🔥 REFERRAL (ОЧЕНЬ ВАЖНО)
    if command.args and command.args.startswith("ref_"):
        try:
            inviter_id = int(command.args.split("_")[1])

            if inviter_id != user.id and not user.invited_by:
                user.invited_by = inviter_id
                await session.commit()

        except Exception:
            pass

    # 👉 Если пользователь пришёл после оплаты
    if command.args and command.args.strip().lower() == "paid":
        await m.answer(
            "✅ Подписка активна!\n\n"
            "Давайте создадим заявку 👇",
            reply_markup=kb_main(is_admin=user.is_admin),
        )
        return

    await m.answer(
        "🚀 Добро пожаловать в PASO\n\n"
        "📦 Отправляй товары через путешественников\n"
        "✈️ Или зарабатывай на доставке\n\n"
        "👇 Выбери действие:",
        reply_markup=kb_main(is_admin=user.is_admin),
    )


# =========================================================
# SUBSCRIBE BUTTON
# =========================================================

@router.callback_query(F.data == "go:subscribe")
async def show_subscribe(cq: CallbackQuery):
    await cq.answer()

    await cq.message.answer(
        "💳 Подписка\n\n"
        "🔓 Открывает контакты\n\n"
        "• Single — 1 контакт (€2)\n"
        "• Standard — 14 дней (€5.55)\n"
        "• Pro — 30 дней (€9)\n\n"
        "👉 Используй /subscribe для оплаты"
    )


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
        "🎁 Приглашай друзей — получай контакты\n\n"
        "💸 Бонусы:\n"
        "• 1 друг → 1 контакт\n\n"

        "🥈 10 друзей → 14 дней доступа\n"
        "👉 экономия €5.55\n\n"

        "🥇 20 друзей → 30 дней доступа\n"
        "👉 экономия €9 🔥\n\n"

        f"👥 Ты пригласил: {user.invites_count}\n\n"
        "🔗 Твоя ссылка:\n"
        f"{ref_link}"
    )

    await cq.message.answer(text)


