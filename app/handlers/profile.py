from __future__ import annotations

from datetime import datetime

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User, Subscription
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
    res = await session.execute(select(User).where(User.tg_user_id == tg_user_id))
    user = res.scalar_one_or_none()

    if not user:
        await answer("Пользователь не найден. Нажмите /start.")
        return

    username = f"@{user.tg_username}" if user.tg_username else "—"
    name = " ".join([x for x in [user.first_name, user.last_name] if x]) or "—"

    # ✅ ПОДПИСКА + админ
    now = datetime.utcnow()
    sub_active = False

    if user.is_admin:
        sub_active = True
        sub_text = "♾ Админ-доступ (без ограничений)"
    else:
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

        if sub and sub.expires_at and sub.expires_at > now:
            sub_active = True
            days_left = (sub.expires_at - now).days
            sub_text = f"✅ Подписка до {_fmt_date(sub.expires_at)} ({days_left} дн.)"
        else:
            sub_text = "❌ Нет подписки\n💳 /subscribe"

    # ⭐ рейтинг
    rating_text = "—"
    if user.rating_count:
        rating_text = f"{user.rating_avg:.2f} ({user.rating_count})"

    # 👑 premium
    premium = "👑 PREMIUM перевозчик" if user.is_premium_carrier else ""

    # 📊 сделки (берём из users)
    deals_customer = user.deals_as_customer or 0
    deals_carrier = user.deals_as_carrier or 0
    deals_total = deals_customer + deals_carrier

    # 💎 ценность
    valuable = user.valuable_count or 0
    max_value = user.max_item_value_eur
    max_value_text = f"{max_value}€" if max_value else "—"

    text = (
        f"👤 {name}\n"
        f"{username}\n\n"
        f"⭐️ Рейтинг: {rating_text}\n\n"
        f"📊 Сделки: {deals_total}\n"
        f"• заказчик: {deals_customer}\n"
        f"• перевозчик: {deals_carrier}\n\n"
        f"{premium}\n"
        f"💎 Ценные: {valuable} (макс: {max_value_text})\n\n"
        f"{sub_text}"
    )

    if sub_active:
        await answer(text, reply_markup=kb_join_group())
    else:
        await answer(text)


@router.message(Command("profile"))
async def profile_cmd(message: Message, session: AsyncSession):
    await render_profile(
        tg_user_id=message.from_user.id,
        answer=message.answer,
        session=session,
    )


@router.callback_query(F.data == "go:profile")
async def profile_cb(cq: CallbackQuery, session: AsyncSession):
    await render_profile(
        tg_user_id=cq.from_user.id,
        answer=cq.message.answer,
        session=session,
    )
    await cq.answer()


@router.callback_query(F.data == "go:join_group")
async def join_group_cb(cq: CallbackQuery, session: AsyncSession):
    res = await session.execute(select(User).where(User.tg_user_id == cq.from_user.id))
    user = res.scalar_one_or_none()

    if not user:
        await cq.answer("Нажмите /start", show_alert=True)
        return

    if not user.is_admin and not await has_active_subscription(session, user.id):
        await cq.answer("Нужна подписка", show_alert=True)
        return

    cfg = load_config()

    link = await create_invite_link(cq.bot, cfg.paso_group_id)
    await cq.message.answer(f"🚪 Вход:\n{link}")
    await cq.answer()

