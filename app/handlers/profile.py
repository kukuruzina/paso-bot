from __future__ import annotations

from datetime import datetime

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User, Subscription, Match, Request, Offer
from ..enums import MatchStatus
from ..services.subscriptions import has_active_subscription, create_invite_link
from ..config import load_config

router = Router()


def kb_join_group():
    b = InlineKeyboardBuilder()
    b.button(text="🚪 Войти в группу", callback_data="go:join_group")
    b.adjust(1)
    return b.as_markup()


def _fmt_date(dt) -> str:
    try:
        return dt.date().isoformat()
    except Exception:
        return str(dt)


async def render_profile(
    *,
    tg_user_id: int,
    answer,
    session: AsyncSession,
) -> None:
    # 1) User
    res = await session.execute(select(User).where(User.tg_user_id == tg_user_id))
    user = res.scalar_one_or_none()
    if not user:
        await answer("Пользователь не найден. Нажмите /start.")
        return

    username = f"@{user.tg_username}" if user.tg_username else "—"
    name = " ".join([x for x in [user.first_name, user.last_name] if x]) or "—"

    # 2) Subscription
    res = await session.execute(
        select(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.status == "active",
        )
        .order_by(Subscription.expires_at.desc())
        .limit(1)
    )
    sub = res.scalar_one_or_none()

    sub_text = "❌ Подписка: нет активной\n💳 Оформить: /subscribe"
    now = datetime.utcnow()

    if sub and sub.expires_at and sub.expires_at > now:
        days_left = (sub.expires_at - now).days
        if days_left < 0:
            days_left = 0

        sub_text = (
            "✅ Подписка: активна\n"
            f"📅 До: {_fmt_date(sub.expires_at)}\n"
            f"⏳ Осталось: {days_left} дней\n"
            "💳 Продлить: /subscribe"
        )

    # 3) Rating
    rating_text = "—"
    if user.rating_count:
        rating_text = f"{user.rating_avg:.2f} ({user.rating_count})"

    premium_badge = "👑 PREMIUM перевозчик" if getattr(user, "is_premium_carrier", False) else "—"

    # 4) Completed deals
    accepted = MatchStatus.accepted

    res = await session.execute(
        select(func.count(Match.id))
        .join(Request, Request.id == Match.request_id)
        .where(
            Request.user_id == user.id,
            Match.status == accepted,
        )
    )
    deals_as_customer = int(res.scalar() or 0)

    res = await session.execute(
        select(func.count(Match.id))
        .join(Offer, Offer.id == Match.offer_id)
        .where(
            Offer.user_id == user.id,
            Match.status == accepted,
        )
    )
    deals_as_carrier = int(res.scalar() or 0)

    deals_total = deals_as_customer + deals_as_carrier

    # 5) Experience stats
    valuable = getattr(user, "valuable_count", 0) or 0
    cash = getattr(user, "cash_count", 0) or 0
    docs = getattr(user, "docs_count", 0) or 0
    max_value = getattr(user, "max_item_value_eur", None)

    max_value_text = "—"
    if max_value:
        max_value_text = f"до {max_value}€"

    text = (
        "👤 Профиль PASО\n\n"
        f"Имя: {name}\n"
        f"Username: {username}\n\n"
        f"⭐️ Рейтинг: {rating_text}\n"
        f"✅ Сделок (accepted): {deals_total}\n"
        f"   • как заказчик: {deals_as_customer}\n"
        f"   • как перевозчик: {deals_as_carrier}\n\n"
        f"{premium_badge}\n"
        f"💎 Ценные посылки: {valuable} (макс: {max_value_text})\n"
        f"💵 Наличные: {cash}\n"
        f"📄 Документы: {docs}\n\n"
        f"{sub_text}"
    )

    active = await has_active_subscription(session, user.id)

    if active:
        await answer(text, reply_markup=kb_join_group())
    else:
        await answer(text)


# ========================
# Команда /profile
# ========================
@router.message(Command("profile"))
async def profile_cmd(message: Message, session: AsyncSession):
    await render_profile(
        tg_user_id=message.from_user.id,
        answer=message.answer,
        session=session,
    )


# ========================
# Кнопка меню "👤 Профиль"
# ========================
@router.message(F.text.in_(["👤 Профиль", "Профиль"]))
async def profile_menu(message: Message, session: AsyncSession):
    await render_profile(
        tg_user_id=message.from_user.id,
        answer=message.answer,
        session=session,
    )


# ========================
# Inline callback (если используется)
# ========================
@router.callback_query(F.data == "go:profile")
async def profile_cb(cq: CallbackQuery, session: AsyncSession):
    await render_profile(
        tg_user_id=cq.from_user.id,
        answer=cq.message.answer,
        session=session,
    )
    await cq.answer()


# ========================
# Кнопка "🚪 Войти в группу"
# ========================
@router.callback_query(F.data == "go:join_group")
async def join_group_cb(cq: CallbackQuery, session: AsyncSession):
    res = await session.execute(select(User).where(User.tg_user_id == cq.from_user.id))
    user = res.scalar_one_or_none()

    if not user:
        await cq.answer("Нажмите /start", show_alert=True)
        return

    if not await has_active_subscription(session, user.id):
        await cq.answer("Нужна активная подписка. Нажмите 💳 Подписка.", show_alert=True)
        return

    cfg = load_config()

    if not getattr(cfg, "paso_group_id", None):
        await cq.answer("PASO_GROUP_ID не настроен", show_alert=True)
        return

    link = await create_invite_link(cq.bot, cfg.paso_group_id)

    await cq.message.answer(f"🚪 Ваша ссылка для входа в группу PASO:\n{link}")

    await cq.answer()
