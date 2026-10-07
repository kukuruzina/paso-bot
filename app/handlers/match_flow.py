from __future__ import annotations

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.paywall import can_access_contacts, spend_contact, spend_contact_no_commit
from app.matching import is_match_valid

from ..models import Match, MatchContactOpen, Request, Offer, User, Review
from ..enums import MatchStatus, RowStatus
from ..config import load_config

# 🔥 НОВЫЕ КНОПКИ
from app.keyboards import kb_deal_result, kb_fail_reasons

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


# =========================================================
# 1️⃣ Предложение сделки (универсально: и заказчик, и исполнитель)
# =========================================================

@router.callback_query(F.data.startswith("match:propose:"))
async def propose_match(cq: CallbackQuery, session: AsyncSession):
    match_id = int(cq.data.split(":")[-1])

    user_res = await session.execute(
        select(User).where(User.tg_user_id == cq.from_user.id)
    )
    user = user_res.scalar_one_or_none()

    if not user or not await can_access_contacts(session, user):
        await cq.answer("Нужен доступ", show_alert=True)
        await cq.message.answer(PAYWALL_TEXT)
        return

    # Lock the match row so concurrent callbacks cannot both process it.
    match = await session.get(
        Match,
        match_id,
        with_for_update=True,
    )

    if not match or match.status != MatchStatus.proposed:
        await cq.answer("Сделка уже обработана", show_alert=True)
        return

    offer = await session.get(Offer, match.offer_id)
    req = await session.get(Request, match.request_id)

    if not req or not offer:
        await cq.answer("Матч больше недоступен", show_alert=True)
        return

    if not is_match_valid(req, offer):
        await cq.answer(
            "Этот матч больше не соответствует условиям",
            show_alert=True,
        )
        return

    offer_user = await session.get(User, offer.user_id)
    req_user = await session.get(User, req.user_id)

    if not offer_user or not req_user:
        await cq.answer(
            "Участник сделки больше недоступен",
            show_alert=True,
        )
        return

    # Only participants can trigger the match.
    if user.id not in (req_user.id, offer_user.id):
        await cq.answer(
            "Вы не участвуете в этой сделке",
            show_alert=True,
        )
        return

    # Spend and status transition are committed together.
    await spend_contact_no_commit(session, user)
    match.status = MatchStatus.pending
    await session.commit()

    await cq.message.edit_reply_markup(reply_markup=None)
    await cq.answer("Предложение отправлено ✅")

    try:
        from app.handlers.request_flow import format_offer_text
        offer_text = format_offer_text(offer, offer_user)
    except Exception as e:
        print("format error:", e)
        offer_text = f"{offer.from_city} → {offer.to_city}"

    if user.id == offer_user.id:
        target_user = req_user
        text_prefix = "📦 Перевозчик предлагает выполнить ваш заказ:"
    else:
        target_user = offer_user
        text_prefix = "📦 Заказчик предлагает вам заказ:"

    await cq.bot.send_message(
        target_user.tg_user_id,
        f"{text_prefix}\n\n{offer_text}\n\n👇 Нажмите кнопку ниже, чтобы принять",
        reply_markup=accept_keyboard(match.id),
    )


# =========================================================
# 2️⃣ Принятие сделки
# =========================================================

@router.callback_query(F.data.startswith("match:accept:"))
async def accept_match(cq: CallbackQuery, session: AsyncSession):
    match_id = int(cq.data.split(":")[-1])

    user_res = await session.execute(
        select(User).where(User.tg_user_id == cq.from_user.id)
    )
    user = user_res.scalar_one_or_none()

    if not user or not await can_access_contacts(session, user):
        await cq.answer("Нужен доступ", show_alert=True)
        await cq.message.answer(PAYWALL_TEXT)
        return

    # Lock the match row so only one accept callback can succeed.
    match = await session.get(
        Match,
        match_id,
        with_for_update=True,
    )

    if not match or match.status != MatchStatus.pending:
        await cq.answer("Сделка уже обработана", show_alert=True)
        return

    req = await session.get(Request, match.request_id)
    offer = await session.get(Offer, match.offer_id)

    if not req or not offer:
        await cq.answer("Матч больше недоступен", show_alert=True)
        return

    if not is_match_valid(req, offer):
        await cq.answer(
            "Этот матч больше не соответствует условиям",
            show_alert=True,
        )
        return

    req_user = await session.get(User, req.user_id)
    offer_user = await session.get(User, offer.user_id)

    if not req_user or not offer_user:
        await cq.answer(
            "Участник сделки больше недоступен",
            show_alert=True,
        )
        return

    # Only participants can accept the match.
    if user.id not in (req_user.id, offer_user.id):
        await cq.answer(
            "Вы не участвуете в этой сделке",
            show_alert=True,
        )
        return

    cfg = load_config()

    if not cfg.deals_chat_id:
        await cq.answer("DEALS_CHAT_ID не настроен", show_alert=True)
        return

    # Create the deal topic before spending the contact.
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

    # Spend contact and finalize the match in one DB transaction.
    await spend_contact_no_commit(session, user)
    match.status = MatchStatus.accepted
    req.status = RowStatus.closed
    await session.commit()

    await cq.message.edit_reply_markup(reply_markup=None)
    await cq.answer("Сделка подтверждена ✅")

    # Send the deal link to both participants.
    for target in (req_user, offer_user):
        try:
            await cq.bot.send_message(
                target.tg_user_id,
                f"💬 Чат сделки: {link}",
            )
        except Exception as e:
            print(f"deal link send error for {target.tg_user_id}: {e}")



# =========================================================
# 🔓 ОТКРЫТЬ КОНТАКТ (PAYWALL)
# =========================================================

@router.callback_query(F.data.startswith("match:contact:"))
async def open_contact(cq: CallbackQuery, session: AsyncSession):
    match_id = int(cq.data.split(":")[-1])

    user_res = await session.execute(
        select(User).where(User.tg_user_id == cq.from_user.id)
    )
    user = user_res.scalar_one_or_none()

    if not user or not await can_access_contacts(session, user):
        await cq.answer("Нужен доступ", show_alert=True)
        await cq.message.answer(PAYWALL_TEXT)
        return

    # Lock the match row so concurrent callbacks cannot both spend a contact.
    match = await session.get(
        Match,
        match_id,
        with_for_update=True,
    )
    if not match:
        await cq.answer("Матч не найден", show_alert=True)
        return

    # Contacts are available only after the deal is accepted.
    if match.status != MatchStatus.accepted:
        await cq.answer(
            "Контакты доступны после подтверждения сделки",
            show_alert=True,
        )
        return

    req = await session.get(Request, match.request_id)
    off = await session.get(Offer, match.offer_id)

    if not req or not off:
        await cq.answer("Матч больше недоступен", show_alert=True)
        return

    # Re-check current matching rules before spending the contact.
    if not is_match_valid(req, off):
        await cq.answer(
            "Этот матч больше не соответствует условиям",
            show_alert=True,
        )
        return

    req_user = await session.get(User, req.user_id)
    off_user = await session.get(User, off.user_id)

    if not req_user or not off_user:
        await cq.answer(
            "Участник сделки больше недоступен",
            show_alert=True,
        )
        return

    # Only participants can open a contact.
    if user.id not in (req_user.id, off_user.id):
        await cq.answer(
            "Вы не участвуете в этой сделке",
            show_alert=True,
        )
        return

    if user.id == req_user.id:
        other = off_user
    else:
        other = req_user

    if not other.tg_username:
        contact_text = (
            "📞 Контакт:\n\n"
            f"👤 {other.first_name or 'Пользователь'}\n"
            "🔗 Username не указан"
        )
    else:
        contact_text = (
            "📞 Контакт:\n\n"
            f"👤 {other.first_name or 'Пользователь'}\n"
            f"🔗 @{other.tg_username.lstrip('@')}"
        )

    # Charge only the first contact opening for this user on this Match.
    contact_open_res = await session.execute(
        select(MatchContactOpen).where(
            MatchContactOpen.match_id == match.id,
            MatchContactOpen.user_id == user.id,
        )
    )
    contact_open = contact_open_res.scalar_one_or_none()

    if contact_open is None:
        session.add(
            MatchContactOpen(
                match_id=match.id,
                user_id=user.id,
            )
        )
        await spend_contact_no_commit(session, user)

    await session.commit()

    await cq.answer("Контакт открыт ✅")
    await cq.message.answer(contact_text)

    try:
        await cq.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


# =========================================================
# 🔥 3️⃣ РЕЗУЛЬТАТ СДЕЛКИ
# =========================================================

@router.callback_query(F.data.startswith("deal:ok:"))
async def deal_ok(
    cq: CallbackQuery,
    session: AsyncSession
):
    match_id = int(cq.data.split(":")[-1])

    # Lock the match so two concurrent confirmations cannot race.
    match = await session.get(
        Match,
        match_id,
        with_for_update=True,
    )
    if not match:
        return await cq.answer(
            "Сделка не найдена",
            show_alert=True
        )

    if match.status != MatchStatus.accepted:
        return await cq.answer(
            "Сделка уже завершена или недоступна",
            show_alert=True
        )

    # текущий пользователь
    result = await session.execute(
        select(User).where(
            User.tg_user_id == cq.from_user.id
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        return await cq.answer(
            "Пользователь не найден",
            show_alert=True
        )

    # Только участник этой сделки может подтвердить её.
    if user.id not in (match.request.user_id, match.offer.user_id):
        return await cq.answer(
            "Вы не участвуете в этой сделке",
            show_alert=True
        )

    # кто подтвердил сделку
    if user.id == match.request.user_id:
        match.requester_result = "success"
    else:
        match.carrier_result = "success"

    await session.commit()

    # если подтвердили оба
    if (
        match.requester_result == "success"
        and
        match.carrier_result == "success"
    ):
        match.status = MatchStatus.completed
        await session.commit()

        await cq.message.answer(
            "🎉 Сделка подтверждена обеими сторонами!"
        )

        # отправляем оценку ОБОИМ
        for tg_id in [
            match.request.user.tg_user_id,
            match.offer.user.tg_user_id
        ]:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=f"{i}⭐",
                            callback_data=f"review:{match.id}:{i}"
                        )
                    ]
                    for i in range(1, 6)
                ]
            )

            await cq.bot.send_message(
                tg_id,
                "⭐ Оцените пользователя",
                reply_markup=kb
            )

        return await cq.answer()

    await cq.message.answer(
        "⏳ Ждём подтверждение второго участника"
    )
    await cq.answer()


@router.callback_query(F.data.startswith("deal:fail:"))
async def deal_fail(
    cq: CallbackQuery,
    session: AsyncSession
):
    match_id = int(cq.data.split(":")[-1])

    # Lock the match so concurrent callbacks cannot race.
    match = await session.get(
        Match,
        match_id,
        with_for_update=True,
    )
    if not match:
        return await cq.answer(
            "Сделка не найдена",
            show_alert=True
        )

    if match.status != MatchStatus.accepted:
        return await cq.answer(
            "Сделка уже завершена или недоступна",
            show_alert=True
        )

    # Проверяем текущего пользователя.
    result = await session.execute(
        select(User).where(
            User.tg_user_id == cq.from_user.id
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        return await cq.answer(
            "Пользователь не найден",
            show_alert=True
        )

    # Только участник этой сделки может её отменить.
    if user.id not in (match.request.user_id, match.offer.user_id):
        return await cq.answer(
            "Вы не участвуете в этой сделке",
            show_alert=True
        )

    match.status = MatchStatus.cancelled
    await session.commit()

    await cq.message.answer(
        "Понятно 👌\n\nЧто пошло не так?",
        reply_markup=kb_fail_reasons(match_id)
    )

    # уведомляем второго участника
    other_tg_id = (
        match.offer.user.tg_user_id
        if cq.from_user.id == match.request.user.tg_user_id
        else match.request.user.tg_user_id
    )

    await cq.bot.send_message(
        other_tg_id,
        "❌ Второй участник отметил сделку как несостоявшуюся"
    )

    await cq.answer()


# =========================================================
# 🔥 4️⃣ ПРИЧИНЫ
# =========================================================

@router.callback_query(F.data.startswith("fail:"))
async def fail_reason(cq: CallbackQuery):

    reason = cq.data.split(":")[1]

    await cq.message.answer(
        "Спасибо за ответ 🙌"
    )

    # TODO:
    # позже можно сохранять причину в БД

    print("FAIL REASON:", reason)

    await cq.answer()


# =========================================================
# ⭐ review логика остаётся как есть
# =========================================================






