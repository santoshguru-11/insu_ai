"""Health checks."""

from __future__ import annotations

import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.health import DatabaseHealth, HealthResponse

logger = get_logger(__name__)

APP_VERSION = "0.1.0"


async def check_database(session: AsyncSession) -> DatabaseHealth:
    """Probe connectivity with a trivial round trip."""
    started = time.perf_counter()
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # health must never raise
        logger.warning("database_health_check_failed", error=str(exc))
        return DatabaseHealth(status="down", latency_ms=None, error=type(exc).__name__)
    latency_ms = round((time.perf_counter() - started) * 1000, 3)
    return DatabaseHealth(status="up", latency_ms=latency_ms)


async def get_health(session: AsyncSession) -> HealthResponse:
    database = await check_database(session)
    return HealthResponse(
        status="ok" if database.status == "up" else "degraded",
        app_name=settings.app_name,
        environment=settings.app_env,
        version=APP_VERSION,
        database=database,
    )
