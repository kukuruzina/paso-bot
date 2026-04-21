import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiohttp import ClientTimeout

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

logger = logging.getLogger(__name__)

cfg = load_config()


async def main():
    logger.info("🚀 Bot starting...")

    # 🔥 ИНИЦИАЛИЗАЦИЯ БД
    init_global_db(cfg.database_url)
    logger.info("✅ Database initialized")

    # 🔥 BOT timeout
    bot = Bot(token=cfg.bot_token)

    dp = Dispatcher()

    # 🔥 MIDDLEWARE
    dp.update.middleware(SubscriptionGateMiddleware())

    # 🔥 ROUTERS
    for r in all_routers():
        dp.include_router(r)

    logger.info("✅ Routers loaded")
    logger.info("🤖 Polling started")

    # 🔥 устойчивый polling (не падает при ошибках сети)
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Polling crashed: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Bot stopped")


