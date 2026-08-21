"""Shared pytest fixtures.

Database-backed tests run against a dedicated database whose name is the
configured one with a `_test` suffix (override with `TEST_DATABASE_URL`). The
schema is built by running the real Alembic migrations, so the tests assert
against exactly what `alembic upgrade head` produces in production.

If no PostgreSQL server is reachable, the db-marked tests are skipped rather
than failed, so `uv run pytest` still works without infrastructure.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from alembic import command
from app.core.config import settings
from app.main import app

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _test_database_url() -> str:
    override = os.getenv("TEST_DATABASE_URL")
    if override:
        return override
    base, _, name = settings.database_url.rpartition("/")
    return f"{base}/{name}_test"


TEST_DATABASE_URL = _test_database_url()


def _admin_url() -> str:
    """Connection to the `postgres` maintenance database."""
    base, _, _ = TEST_DATABASE_URL.rpartition("/")
    return f"{base}/postgres"


async def _database_reachable() -> bool:
    engine = create_async_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        await engine.dispose()


async def _recreate_test_database() -> None:
    _, _, db_name = TEST_DATABASE_URL.rpartition("/")
    engine = create_async_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :name AND pid <> pg_backend_pid()"
            ),
            {"name": db_name},
        )
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    await engine.dispose()


def _run_migrations() -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
async def migrated_database() -> AsyncGenerator[str, None]:
    """A freshly migrated test database; skips the test if PostgreSQL is absent."""
    if not await _database_reachable():
        pytest.skip(f"PostgreSQL is not reachable at {_admin_url()}")

    await _recreate_test_database()

    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    try:
        # alembic/env.py calls asyncio.run(), which cannot nest inside the
        # loop this fixture already runs in — give it a thread of its own.
        await asyncio.to_thread(_run_migrations)
        yield TEST_DATABASE_URL
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


@pytest.fixture(scope="session")
async def db_engine(migrated_database: str) -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(migrated_database)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def db_connection(db_engine: AsyncEngine) -> AsyncGenerator[AsyncConnection, None]:
    async with db_engine.connect() as connection:
        yield connection


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """HTTP client wired straight to the ASGI app (no network involved)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


@pytest.fixture
def expected_tables() -> Iterator[set[str]]:
    yield {
        "assets",
        "incidents",
        "agent_runs",
        "diagnoses",
        "evidence_items",
        "maintenance_proposals",
        "part_checks",
        "approval_decisions",
        "work_orders",
        "technician_outcomes",
        "audit_events",
    }
