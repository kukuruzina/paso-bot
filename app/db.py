from __future__ import annotations

from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()

_engine = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def make_engine(database_url: str):
    return create_async_engine(
        database_url,
        echo=False,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )


def make_session_factory(engine):
    return async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )


def init_global_db(database_url: str) -> None:
    """
    Инициализация глобального engine и sessionmaker
    """
    global _engine, _session_maker

    _engine = make_engine(database_url)
    _session_maker = make_session_factory(_engine)


@asynccontextmanager
async def get_session():
    """
    Получение глобальной сессии
    """
    if _session_maker is None:
        raise RuntimeError(
            "Database not initialized. Call init_global_db() first."
        )

    async with _session_maker() as session:
        yield session
