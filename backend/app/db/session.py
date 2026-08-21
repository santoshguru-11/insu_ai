"""Async engine, session factory and the FastAPI database dependency.

The engine is built lazily on first use rather than at import time, so the
process can be pointed at a different database (the test harness does exactly
that) without having to control module import order.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_database_url: str | None = None


def _build_engine(url: str) -> AsyncEngine:
    return create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


def get_engine() -> AsyncEngine:
    """The process-wide engine, created on first call."""
    global _engine, _database_url
    if _engine is None:
        _database_url = _database_url or settings.database_url
        _engine = _build_engine(_database_url)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """The process-wide session factory, bound to `get_engine()`."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def configure(url: str) -> None:
    """Point the process at `url`, disposing whatever engine it held before.

    Used by the test harness to redirect the application at a scratch database.
    """
    global _engine, _session_factory, _database_url
    await dispose_engine()
    _database_url = url
    _engine = None
    _session_factory = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a session bound to the request lifetime.

    The session is committed when the handler returns normally and rolled back
    if it raises, so route code never has to manage the transaction itself —
    and a failed request can never leave a partial write behind.
    """
    async with get_session_factory()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()


async def dispose_engine() -> None:
    """Close pooled connections — called on application shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
