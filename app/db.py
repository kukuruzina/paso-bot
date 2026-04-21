from __future__ import annotations

from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)
from sqlalchemy.orm import declarative_base

from app.config import load_config

Base = declarative_base()

_engine = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


# =========================================================
# 🔧 FACTORIES
# =========================================================

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


# =========================================================
# 🚀 INIT
# =========================================================

def init_global_db(database_url: str | None = None) -> None:
    """
    Инициализация глобального engine и sessionmaker
    """
    global _engine, _session_maker

    if _engine is not None:
        return  # уже инициализировано

    if not database_url:
        cfg = load_config()
        database_url = cfg.database_url

    _engine = make_engine(database_url)
    _session_maker = make_session_factory(_engine)


def get_engine():
    """
    Безопасное получение engine
    """
    if _engine is None:
        init_global_db()
    return _engine


# =========================================================
# 📦 SESSION
# =========================================================

@asynccontextmanager
async def get_session():
    """
    Получение глобальной сессии
    """
    if _session_maker is None:
        init_global_db()

    async with _session_maker() as session:
        yield session

