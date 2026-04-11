from __future__ import annotations

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from app.db import get_session
from app.models import User
from app.services.subscriptions import has_active_subscription
from sqlalchemy import select


class SubscriptionGateMiddleware(BaseMiddleware):

    async def __call__(self, handler, event: TelegramObject, data: dict):

        # 🔥 ВСЕГДА создаём session и прокидываем дальше
        async with get_session() as session:
            data["session"] = session

            # пропускаем не-message события
            if not isinstance(event, (Message, CallbackQuery)):
                return await handler(event, data)

            tg_user_id = event.from_user.id if event.from_user else None
            if not tg_user_id:
                return await handler(event, data)

            text = ""
            if isinstance(event, Message):
                text = event.text or ""
            elif isinstance(event, CallbackQuery):
                text = event.data or ""

            # ✅ РАЗРЕШЁННЫЕ БЕЗ ПОДПИСКИ
            allow_prefixes = (
                "/start",
                "/profile",
                "/subscribe",
                "go:profile",
                "go:req",
                "go:off",

                # request flow
                "cat:",
                "w:",
                "c:",
                "d:",
                "req:confirm",

                # offer flow
                "date:",
                "cal:",
                "off:confirm_rules",
            )

            if any(text.startswith(x) for x in allow_prefixes):
                return await handler(event, data)

            # 🔒 проверка подписки
            res = await session.execute(
                select(User).where(User.tg_user_id == tg_user_id)
            )
            user = res.scalar_one_or_none()

            if not user:
                return await handler(event, data)

            active = await has_active_subscription(session, user.id)

            if active:
                return await handler(event, data)

            # ❌ блокируем доступ
            if isinstance(event, Message):
                await event.answer("🔒 Доступ по подписке. Оформить: /subscribe")
            else:
                await event.answer(
                    "🔒 Доступ по подписке. Оформить: /subscribe",
                    show_alert=True
                )

            return

