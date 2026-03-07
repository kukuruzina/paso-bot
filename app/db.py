from __future__ import annotations

from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# Глобальные (инициализируются в main)
_engine = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def make_engine(database_url: str):
    return create_async_engine(
        database_url,
        echo=False,
        future=True,
    )


def make_session_factory(engine):
    return async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )


def init_global_db(database_url: str) -> None:
    """
    Инициализирует глобальные engine + sessionmaker (чтобы get_session работал).
    """
    global _engine, _session_maker
    _engine = make_engine(database_url)
    _session_maker = make_session_factory(_engine)


@asynccontextmanager
async def get_session():
    """
    Глобальная сессия. Перед использованием должен быть вызван init_global_db().
    """
    if _session_maker is None:
        raise RuntimeError("DB is not initialized. Call init_global_db(database_url) first.")
    async with _session_maker() as session:
        yield session