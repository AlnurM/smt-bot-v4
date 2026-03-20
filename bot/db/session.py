"""Async SQLAlchemy engine factory and session context manager."""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bot.config import settings


def _ensure_asyncpg_url(url: str) -> str:
    """Convert postgresql:// to postgresql+asyncpg:// if needed.

    Railway and other PaaS providers give DATABASE_URL with the sync driver.
    Our app requires asyncpg.
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


engine = create_async_engine(
    _ensure_asyncpg_url(settings.database_url.get_secret_value()),
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
