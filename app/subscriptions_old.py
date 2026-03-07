from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Subscription


async def has_active_subscription(session: AsyncSession, user_id: int) -> bool:
    """True если есть активная подписка с expires_at > сейчас."""
    now = datetime.utcnow()
    q = (
        select(Subscription)
        .where(
            Subscription.user_id == user_id,
            Subscription.status == "active",
            Subscription.expires_at > now,
        )
        .order_by(Subscription.expires_at.desc())
        .limit(1)
    )
    sub = (await session.execute(q)).scalar_one_or_none()
    return sub is not None


async def activate_subscription(
    session: AsyncSession,
    *,
    user_id: int,
    duration_days: int,
    source: str,
) -> Subscription:
    """
    Создаёт/продлевает подписку:
    - если активная есть → продлеваем от max(now, expires_at)
    - иначе → начинаем от now
    """
    now = datetime.utcnow()

    q = (
        select(Subscription)
        .where(
            Subscription.user_id == user_id,
            Subscription.status == "active",
        )
        .order_by(Subscription.expires_at.desc())
        .limit(1)
    )
    current = (await session.execute(q)).scalar_one_or_none()

    start_from = now
    if current and current.expires_at and current.expires_at > now:
        start_from = current.expires_at

    new_sub = Subscription(
        user_id=user_id,
        status="active",
        started_at=now,
        expires_at=start_from + timedelta(days=duration_days),
        source=source,
        created_at=now,
    )

    session.add(new_sub)
    await session.commit()
    await session.refresh(new_sub)
    return new_sub


async def create_invite_link(bot, chat_id: int) -> str:
    """
    Делает одноразовую ссылку в группу/супергруппу.
    Боту нужны права админа на создание invite link.
    """
    link = await bot.create_chat_invite_link(
        chat_id=chat_id,
        member_limit=1,
        creates_join_request=False,
    )
    return link.invite_link