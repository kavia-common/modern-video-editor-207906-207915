from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.api.settings import get_settings

_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


# PUBLIC_INTERFACE
def get_engine() -> AsyncEngine:
    """Create (or return) the global Async SQLAlchemy engine.

    Returns:
        AsyncEngine: SQLAlchemy async engine connected to PostgreSQL.
    """
    global _engine, _session_maker
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.db_url,
            pool_pre_ping=True,
        )
        _session_maker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


# PUBLIC_INTERFACE
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an AsyncSession per request."""
    global _session_maker
    if _session_maker is None:
        get_engine()
    assert _session_maker is not None
    async with _session_maker() as session:
        yield session
