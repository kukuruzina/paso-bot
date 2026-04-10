from __future__ import annotations

from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Subscription


async def has_active_subscription(session: AsyncSession, user_id: int) -> bool:
    """True если есть активная подписка."""
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
    """Активирует или продлевает подписку."""

    now = datetime.utcnow()

    # ищем последнюю активную подписку
    q = (
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .order_by(Subscription.expires_at.desc())
        .limit(1)
    )

    last_sub = (await session.execute(q)).scalar_one_or_none()

    if last_sub and last_sub.expires_at and last_sub.expires_at > now:
        # продлеваем от текущего expires_at
        new_expires = last_sub.expires_at + timedelta(days=duration_days)
    else:
        # новая подписка
        new_expires = now + timedelta(days=duration_days)

    new_sub = Subscription(
        user_id=user_id,
        status="active",
        started_at=now,
        expires_at=new_expires,
        source=source,
    )

    session.add(new_sub)
    await session.commit()
    await session.refresh(new_sub)

    return new_sub



