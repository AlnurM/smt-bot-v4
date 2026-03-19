"""Async SQLAlchemy engine factory and session context manager."""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bot.config import settings

engine = create_async_engine(
    settings.database_url.get_secret_value(),
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context-manager session — use as `async with get_session() as session:`."""
    async with SessionLocal() as session:
        yield session
