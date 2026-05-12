from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from datetime import datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import load_config
from ..models import User, Request, Offer, Match

router = Router()


# =========================================================
# CHAT ID
# =========================================================

@router.message(Command("chatid"))
async def get_chat_id(m: Message):
    await m.answer(
        f"Chat ID:\n"
        f"{m.chat.id}\n\n"
        f"Chat type: {m.chat.type}"
    )


# =========================================================
# /stats COMMAND
# =========================================================

@router.message(lambda m: (m.text or "").strip() == "/stats")
async def stats(m: Message, session: AsyncSession):
    cfg = load_config()

    if m.from_user.id not in cfg.admin_tg_ids:
        return

    users_cnt = (await session.execute(
        select(func.count(User.id))
    )).scalar() or 0

    req_cnt = (await session.execute(
        select(func.count(Request.id))
    )).scalar() or 0

    off_cnt = (await session.execute(
        select(func.count(Offer.id))
    )).scalar() or 0

    match_cnt = (await session.execute(
        select(func.count(Match.id))
    )).scalar() or 0

    await m.answer(
        "📊 PASO статистика\n\n"
        f"👥 Пользователей: {users_cnt}\n"
        f"📦 Заявок: {req_cnt}\n"
        f"🧳 Поездок: {off_cnt}\n"
        f"🤝 Matches: {match_cnt}"
    )


# =========================================================
# PROFILE BUTTON → ADMIN STATS
# =========================================================

@router.callback_query(F.data == "go:stats")
async def admin_stats_callback(
    cq: CallbackQuery,
    session: AsyncSession
):
    cfg = load_config()

    if cq.from_user.id not in cfg.admin_tg_ids:
        return

    users_cnt = (await session.execute(
        select(func.count(User.id))
    )).scalar() or 0

    req_cnt = (await session.execute(
        select(func.count(Request.id))
    )).scalar() or 0

    off_cnt = (await session.execute(
        select(func.count(Offer.id))
    )).scalar() or 0

    match_cnt = (await session.execute(
        select(func.count(Match.id))
    )).scalar() or 0

    today = datetime.utcnow() - timedelta(days=1)
    week = datetime.utcnow() - timedelta(days=7)

    new_today = (await session.execute(
        select(func.count(User.id))
        .where(User.created_at >= today)
    )).scalar() or 0

    new_week = (await session.execute(
        select(func.count(User.id))
        .where(User.created_at >= week)
    )).scalar() or 0

    await cq.message.answer(
        "📊 PASO статистика\n\n"

        f"👥 Пользователей: {users_cnt}\n"
        f"└ +{new_today} сегодня / +{new_week} за неделю\n\n"

        f"📦 Заявок: {req_cnt}\n"
        f"🧳 Поездок: {off_cnt}\n"
        f"🤝 Matches: {match_cnt}"
    )

    await cq.answer()


