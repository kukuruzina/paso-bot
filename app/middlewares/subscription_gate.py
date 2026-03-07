from __future__ import annotations

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from app.db import get_session
from app.models import User
from app.services.subscriptions import has_active_subscription
from sqlalchemy import select


class SubscriptionGateMiddleware(BaseMiddleware):
    """
    Пример: блокируем только часть действий без подписки.
    Сейчас — просто пример, можно расширять.
    """

    async def __call__(self, handler, event: TelegramObject, data: dict):
        # пропускаем не Message/CallbackQuery
        if not isinstance(event, (Message, CallbackQuery)):
            return await handler(event, data)

        tg_user_id = event.from_user.id if event.from_user else None
        if not tg_user_id:
            return await handler(event, data)

        # тут можно сделать allowlist команд типа /start /profile /subscribe и т.д.
        text = ""
        if isinstance(event, Message):
            text = event.text or ""
        elif isinstance(event, CallbackQuery):
            text = event.data or ""

        allow_prefixes = ("/start", "/profile", "/subscribe", "go:profile", "go:subscribe")
        if any(text.startswith(x) for x in allow_prefixes):
            return await handler(event, data)

        # проверка подписки
        async with get_session() as session:
            res = await session.execute(select(User).where(User.tg_user_id == tg_user_id))
            user = res.scalar_one_or_none()
            if not user:
                return await handler(event, data)

            active = await has_active_subscription(session, user.id)
            if active:
                return await handler(event, data)

        # если нет подписки — блок
        if isinstance(event, Message):
            await event.answer("🔒 Доступ по подписке. Оформить: /subscribe")
        else:
            await event.answer("🔒 Доступ по подписке. Оформить: /subscribe", show_alert=True)

        return
