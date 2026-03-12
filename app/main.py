import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from .config import load_config
from .db import (
    make_engine,
    make_session_factory,
    Base,
    init_global_db,
)
from .handlers import all_routers


async def on_startup(bot: Bot):
    await bot.set_my_commands([
        BotCommand(command="start", description="Start"),
        BotCommand(command="profile", description="Profile"),
        BotCommand(command="subscribe", description="Subscribe"),
        BotCommand(command="stats", description="Admin stats"),
    ])


async def create_tables(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def session_middleware(session_factory):
    from aiogram import BaseMiddleware
    from typing import Callable, Any, Awaitable, Dict

    class DBSessionMiddleware(BaseMiddleware):
        async def __call__(
            self,
            handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
            event: Any,
            data: Dict[str, Any],
        ) -> Any:
            async with session_factory() as session:
                data["session"] = session
                return await handler(event, data)

    return DBSessionMiddleware()


async def main():
    logging.basicConfig(level=logging.INFO)

    cfg = load_config()

    # 🔎 Логируем строку подключения
    print("DATABASE_URL =", cfg.database_url, flush=True)

    # Инициализируем глобальную БД
    init_global_db(cfg.database_url)

    # Создаём engine и session factory
    engine = make_engine(cfg.database_url)
    session_factory = make_session_factory(engine)

    # Создаём таблицы если их нет
    await create_tables(engine)

    bot = Bot(
        token=cfg.bot_token,
        default=DefaultBotProperties(parse_mode="HTML"),
    )

    dp = Dispatcher(storage=MemoryStorage())

    # middleware БД
    dp.update.middleware(session_middleware(session_factory))

    # подключаем роутеры
    for router in all_routers():
        dp.include_router(router)

    await on_startup(bot)

    # важно для polling
    await bot.delete_webhook(drop_pending_updates=True)

    print("✅ Bot started (polling)...", flush=True)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
