from aiogram import Router
from aiogram.types import Message
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import load_config
from ..models import User, Request, Offer, Match

router = Router()

from aiogram.filters import Command
from aiogram.types import Message


@router.message(Command("chatid"))
async def get_chat_id(m: Message):
    await m.answer(
        f"Chat ID:\n"
        f"{m.chat.id}\n\n"
        f"Chat type: {m.chat.type}"
    )

@router.message(lambda m: (m.text or "").strip() == "/stats")
async def stats(m: Message, session: AsyncSession):
    cfg = load_config()

    if m.from_user.id not in cfg.admin_tg_ids:
        return

    users_cnt = (await session.execute(select(func.count(User.id)))).scalar() or 0
    req_cnt = (await session.execute(select(func.count(Request.id)))).scalar() or 0
    off_cnt = (await session.execute(select(func.count(Offer.id)))).scalar() or 0
    match_cnt = (await session.execute(select(func.count(Match.id)))).scalar() or 0

    await m.answer(
        "📊 PASO /stats\n\n"
        f"👤 Users: {users_cnt}\n"
        f"📦 Requests: {req_cnt}\n"
        f"✈️ Offers: {off_cnt}\n"
        f"🔗 Matches: {match_cnt}\n"
    )
