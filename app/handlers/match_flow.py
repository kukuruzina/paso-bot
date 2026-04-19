from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.paywall import can_access_contacts, spend_contact  # 🔥 NEW

from ..models import Match, Request, Offer, User, Review
from ..enums import MatchStatus, RowStatus
from ..config import load_config

router = Router()

PAYWALL_TEXT = (
    "🔒 Доступ к сделкам закрыт\n\n"
    "💳 Оформите подписку или купите доступ:\n"
    "/subscribe"
)


# =========================================================
# helpers
# =========================================================

def topic_link(chat_id: int, thread_id: int) -> str:
    internal = str(chat_id).replace("-100", "")
    return f"https://t.me/c/{internal}/{thread_id}"


async def create_deal_topic(bot, chat_id: int, title: str):
    topic = await bot.create_forum_topic(chat_id=chat_id, name=title)
    thread_id = topic.message_thread_id
    link = topic_link(chat_id, thread_id)
    return thread_id, link


def accept_keyboard(match_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="✅ Принять сделку", callback_data=f"match:accept:{match_id}")
    b.adjust(1)
    return b.as_markup()


def rating_keyboard(match_id: int):
    b = InlineKeyboardBuilder()
    for i in range(1, 6):
        b.button(text=f"⭐️ {i}", callback_data=f"review:rate:{match_id}:{i}")
    b.adjust(5)
    return b.as_markup()


def value_keyboard(match_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="до 1000€", callback_data=f"review:value:{match_id}:1000")
    b.button(text="до 5000€", callback_data=f"review:value:{match_id}:5000")
    b.button(text="до 10000€", callback_data=f"review:value:{match_id}:10000")
    b.button(text="не ценно", callback_data=f"review:value:{match_id}:0")
    b.adjust(2, 2)
    return b.as_markup()


def yes_no_keyboard(prefix: str, match_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="✅ Да", callback_data=f"{prefix}:{match_id}:1")
    b.button(text="❌ Нет", callback_data=f"{prefix}:{match_id}:0")
    b.adjust(2)
    return b.as_markup()


# =========================================================
# 1️⃣ Заказчик предлагает сделку
# =========================================================

@router.callback_query(F.data.startswith("match:propose:"))
async def propose_match(cq: CallbackQuery, session: AsyncSession):
    match_id = int(cq.data.split(":")[-1])
    match = await session.get(Match, match_id)

    user_res = await session.execute(
        select(User).where(User.tg_user_id == cq.from_user.id)
    )
    user = user_res.scalar_one_or_none()

    # 🔥 PAYWALL
    if not user or not await can_access_contacts(session, user):
        await cq.answer("Нужен доступ", show_alert=True)
        await cq.message.answer(PAYWALL_TEXT)
        return

    # 🔥 списание контакта (single)
    await spend_contact(session, user)

    if not match or match.status != MatchStatus.proposed:
        await cq.answer("Сделка уже обработана", show_alert=True)
        return

    offer = await session.get(Offer, match.offer_id)
    offer_user = await session.get(User, offer.user_id)

    match.status = MatchStatus.pending
    await session.commit()

    await cq.message.edit_reply_markup(reply_markup=None)
    await cq.answer("Предложение отправлено исполнителю ✅")

    await cq.bot.send_message(
        offer_user.tg_user_id,
        "📦 Вам предложили сделку.\n\nНажмите кнопку ниже, чтобы принять.",
        reply_markup=accept_keyboard(match.id),
    )


# =========================================================
# 2️⃣ Исполнитель принимает
# =========================================================

@router.callback_query(F.data.startswith("match:accept:"))
async def accept_match(cq: CallbackQuery, session: AsyncSession):
    match_id = int(cq.data.split(":")[-1])
    match = await session.get(Match, match_id)

    user_res = await session.execute(
        select(User).where(User.tg_user_id == cq.from_user.id)
    )
    user = user_res.scalar_one_or_none()

    # 🔥 PAYWALL
    if not user or not await can_access_contacts(session, user):
        await cq.answer("Нужен доступ", show_alert=True)
        await cq.message.answer(PAYWALL_TEXT)
        return

    # 🔥 списание контакта (single)
    await spend_contact(session, user)

    if not match or match.status != MatchStatus.pending:
        await cq.answer("Сделка уже обработана", show_alert=True)
        return

    req = await session.get(Request, match.request_id)
    offer = await session.get(Offer, match.offer_id)

    req_user = await session.get(User, req.user_id)
    offer_user = await session.get(User, offer.user_id)

    cfg = load_config()
    if not cfg.deals_chat_id:
        await cq.answer("DEALS_CHAT_ID не настроен", show_alert=True)
        return

    try:
        thread_id, link = await create_deal_topic(
            bot=cq.bot,
            chat_id=cfg.deals_chat_id,
            title=f"{req.from_city} → {req.to_city} • #{match.id}",
        )
    except TelegramBadRequest:
        await cq.answer("Ошибка создания темы", show_alert=True)
        return

    await cq.bot.send_message(
        chat_id=cfg.deals_chat_id,
        message_thread_id=thread_id,
        text="🧩 Новая сделка PASO",
    )

    await cq.bot.send_message(req_user.tg_user_id, f"💬 Чат сделки: {link}")
    await cq.bot.send_message(offer_user.tg_user_id, f"💬 Чат сделки: {link}")

    match.status = MatchStatus.accepted
    req.status = RowStatus.closed

    await session.commit()

    await cq.message.edit_reply_markup(reply_markup=None)
    await cq.answer("Сделка подтверждена ✅")

    await cq.bot.send_message(
        req_user.tg_user_id,
        "⭐️ Поставьте оценку путешественнику:",
        reply_markup=rating_keyboard(match.id),
    )


# =========================================================
# остальной код (review) НЕ ТРОГАЕМ
# =========================================================

