from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment, Subscription, User
from app.plans import get_plan


async def fulfill_payment(
    session: AsyncSession,
    *,
    provider: str,
    external_id: str,
    tg_user_id: int,
    plan_key: str,
    amount_minor: int,
    currency: str,
) -> bool:
    """
    Начисляет оплаченный тариф ровно один раз.
    Возвращает True при новом начислении, False при повторном webhook.
    Вызывающий код должен передавать только подтверждённый платёж.
    """
    plan = get_plan(plan_key)
    if plan is None:
        raise ValueError(f"Unknown plan: {plan_key}")

    if provider not in {"stripe", "yookassa"}:
        raise ValueError(f"Unknown payment provider: {provider}")

    if not external_id or len(external_id) > 128:
        raise ValueError("Invalid external payment ID")

    if amount_minor <= 0:
        raise ValueError("Payment amount must be positive")

    if not currency or len(currency) > 8:
        raise ValueError("Invalid currency")

    async with session.begin():
        user_result = await session.execute(
            select(User)
            .where(User.tg_user_id == tg_user_id)
            .with_for_update()
        )
        user = user_result.scalar_one_or_none()
        if user is None:
            raise ValueError(f"User not found: {tg_user_id}")

        payment_insert = (
            insert(Payment)
            .values(
                user_id=user.id,
                provider=provider,
                amount=amount_minor,
                currency=currency.upper(),
                status="succeeded",
                external_id=external_id,
                created_at=datetime.utcnow(),
            )
            .on_conflict_do_nothing(
                index_elements=["provider", "external_id"],
                index_where=Payment.external_id.is_not(None),
            )
            .returning(Payment.id)
        )

        payment_result = await session.execute(payment_insert)
        payment_id = payment_result.scalar_one_or_none()

        if payment_id is None:
            return False

        now = datetime.utcnow()
        duration_days = int(plan["duration_days"])
        contacts = int(plan["contacts"])

        if contacts > 0:
            user.contacts_left = (user.contacts_left or 0) + contacts

        if duration_days > 0:
            subscription_result = await session.execute(
                select(Subscription)
                .where(Subscription.user_id == user.id)
                .order_by(Subscription.expires_at.desc())
                .limit(1)
            )
            last_subscription = subscription_result.scalar_one_or_none()

            if (
                last_subscription is not None
                and last_subscription.expires_at > now
            ):
                expires_at = last_subscription.expires_at + timedelta(
                    days=duration_days
                )
            else:
                expires_at = now + timedelta(days=duration_days)

            session.add(
                Subscription(
                    user_id=user.id,
                    status="active",
                    started_at=now,
                    expires_at=expires_at,
                    source=provider,
                )
            )

    return True
