from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import load_config
from ..models import User, Subscription
from ..services.subscriptions import create_invite_link

router = Router()


def is_admin(tg_id: int) -> bool:
    cfg = load_config()
    return tg_id in cfg.admin_tg_ids


@router.message(Command("sub_add"))
async def sub_add(message: Message, session: AsyncSession):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.answer(
            "Использование:\n"
            "/sub_add @username 30\n"
            "или\n"
            "/sub_add 123456789 30"
        )
        return

    who = parts[1].strip()
    days_raw = parts[2].strip()

    try:
        days = int(days_raw)
        if days <= 0:
            raise ValueError
    except Exception:
        await message.answer("Дни должны быть числом больше 0.")
        return

    user = None

    # По tg_user_id
    if who.isdigit():
        tg_id = int(who)
        res = await session.execute(
            select(User).where(User.tg_user_id == tg_id)
        )
        user = res.scalar_one_or_none()

    # По username
    if not user and who.startswith("@"):
        uname = who[1:].lower()
        res = await session.execute(
            select(User).where(User.tg_username.ilike(uname))
        )
        user = res.scalar_one_or_none()

    if not user:
        await message.answer(
            "Пользователь не найден.\n"
            "Он должен хотя бы раз нажать /start."
        )
        return

    # Создаём подписку
    sub = Subscription(
        user_id=user.id,
        status="active",
        started_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=days),
        source="manual",
    )

    session.add(sub)
    await session.commit()

    await message.answer(f"✅ Подписка активирована для {who} на {days} дней.")
    await message.bot.send_message(
        user.tg_user_id,
        f"✅ Вам активировали подписку PASO на {days} дней."
    )

    # Отправляем ссылку в группу
    cfg = load_config()
    if cfg.paso_group_id:
        link = await create_invite_link(message.bot, cfg.paso_group_id)
        await message.bot.send_message(
            user.tg_user_id,
            f"🚪 Ваша ссылка для входа в группу PASO:\n{link}"
        )