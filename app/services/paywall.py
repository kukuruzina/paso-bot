from sqlalchemy import select
from datetime import datetime

from app.models import Subscription
from app.config import load_config

cfg = load_config()


async def can_access_contacts(session, user) -> bool:

    # ADMIN BYPASS
    if user.is_admin:
        return True

    if user.tg_user_id in cfg.admin_tg_ids:
        return True

    # SINGLE CONTACTS
    if (user.contacts_left or 0) > 0:
        return True

    # ACTIVE SUBSCRIPTION
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

    if sub and sub.expires_at and sub.expires_at > datetime.utcnow():
        return True

    return False


async def spend_contact(session, user):

    # ADMIN BYPASS
    if user.is_admin:
        return

    if user.tg_user_id in cfg.admin_tg_ids:
        return

    # SPEND SINGLE CONTACT
    if (user.contacts_left or 0) > 0:
        user.contacts_left -= 1
        await session.commit()

