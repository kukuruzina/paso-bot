import asyncio

from app.db import get_engine
from app.models import Base


async def main():
    engine = get_engine()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("✅ Таблицы созданы")


if __name__ == "__main__":
    asyncio.run(main())

