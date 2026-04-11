import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.config import load_config
from app.handlers import all_routers
from app.middlewares.subscription_gate import SubscriptionGateMiddleware
from app.db import init_global_db

# ======================
# CONFIG
# ======================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

cfg = load_config()


async def main():
    print("🚀 Bot starting...")

    # 🔥 ИНИЦИАЛИЗАЦИЯ БД (БЕЗ await !!!)
    init_global_db(cfg.database_url)
    print("✅ Database initialized")

    bot = Bot(token=cfg.bot_token)
    dp = Dispatcher()

    # 🔥 MIDDLEWARE (даёт session в handlers)
    dp.update.middleware(SubscriptionGateMiddleware())

    # 🔥 ROUTERS
    for r in all_routers():
        dp.include_router(r)

    print("✅ Routers loaded")
    print("🤖 Polling started")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
