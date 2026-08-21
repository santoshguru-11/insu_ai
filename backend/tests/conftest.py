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
from app.db import session as db_session
from app.main import app
from app.models.enums import ScenarioType
from app.models.incident import Incident
from app.seed.demo import seed

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


@pytest.fixture(scope="session")
async def app_database(migrated_database: str) -> AsyncGenerator[str, None]:
    """Point the application itself at the scratch database.

    Everything the app opens a session through — the request dependency, the
    WebSocket snapshot loader, and the out-of-band audit writer — resolves the
    factory at call time, so this one call redirects all of them.
    """
    await db_session.configure(migrated_database)
    try:
        yield migrated_database
    finally:
        await db_session.dispose_engine()


@pytest.fixture
async def seeded(app_database: str) -> AsyncGenerator[dict[str, Incident], None]:
    """Fresh demo data, keyed by scenario, for one test.

    Re-seeding per test keeps cases independent: a test that approves the main
    incident cannot leave it approved for the next one.
    """
    incidents = await seed(reset=True)
    yield {str(incident.scenario_type): incident for incident in incidents}


@pytest.fixture
def main_incident(seeded: dict[str, Incident]) -> Incident:
    """Scenario A — the `approval_required` demo incident, trace `tr_9f21`."""
    return seeded[str(ScenarioType.NORMAL)]


@pytest.fixture
def low_confidence_incident(seeded: dict[str, Incident]) -> Incident:
    """Scenario B — parked in `human_review`."""
    return seeded[str(ScenarioType.LOW_CONFIDENCE)]


@pytest.fixture
def offline_incident(seeded: dict[str, Incident]) -> Incident:
    """Scenario C — diagnosed at the edge with the cloud link down."""
    return seeded[str(ScenarioType.OFFLINE)]


@pytest.fixture
def api_prefix() -> str:
    return settings.api_prefix


@pytest.fixture
async def in_test_client(app_database: str) -> AsyncGenerator[object, None]:
    """Run a `starlette.testclient.TestClient` block on its own event loop.

    `TestClient` (needed for WebSocket support) drives the app from a private
    loop in a worker thread, and asyncpg connections cannot cross event loops.
    So the shared engine is torn down before the block and its module state is
    cleared afterwards — the next fixture that needs it rebuilds it on whichever
    loop is then current.
    """

    async def _run(fn):
        await db_session.dispose_engine()
        try:
            return await asyncio.to_thread(fn)
        finally:
            # The engine now belongs to the TestClient's finished loop; drop the
            # references rather than awaiting a dispose that loop can no longer run.
            db_session._engine = None
            db_session._session_factory = None

    yield _run


@pytest.fixture
def audit_since(api: AsyncClient):
    """Return only the audit events an incident gained after this point.

    The trail is append-only and the seed reuses incident rows, so events from
    earlier runs legitimately remain attached. Tests therefore assert on the
    slice they caused rather than on the whole timeline.
    """

    async def _watermark(incident_id) -> int:
        response = await api.get(f"/incidents/{incident_id}/audit", params={"limit": 500})
        return int(response.json()["total"])

    async def _since(incident_id, watermark: int) -> list[dict]:
        response = await api.get(f"/incidents/{incident_id}/audit", params={"limit": 500})
        return response.json()["items"][watermark:]

    _since.watermark = _watermark  # type: ignore[attr-defined]
    return _since


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
async def api(app_database: str) -> AsyncGenerator[AsyncClient, None]:
    """Client for the versioned API, with the app pointed at the test database."""
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url=f"http://testserver{settings.api_prefix}"
    ) as async_client:
        yield async_client


@pytest.fixture
def expected_tables() -> Iterator[set[str]]:
    yield {
        "sentinel_anomalies",
        "diagnosis_alternatives",
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
