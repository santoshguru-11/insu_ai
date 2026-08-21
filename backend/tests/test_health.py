"""Tests for GET /health."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.config import settings


@pytest.mark.db
@pytest.mark.parametrize("path", ["/health", "/api/v1/health"])
async def test_health_reports_ok_with_database_up(
    client: AsyncClient, migrated_database: str, path: str
) -> None:
    response = await client.get(path)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == settings.app_env
    assert body["app_name"] == settings.app_name
    assert body["database"]["status"] == "up"
    assert body["database"]["latency_ms"] >= 0


@pytest.mark.db
async def test_health_is_served_under_the_configured_prefix(
    client: AsyncClient, migrated_database: str
) -> None:
    response = await client.get(f"{settings.api_prefix}/health")
    assert response.status_code == 200


async def test_health_response_shape_is_stable(client: AsyncClient) -> None:
    """The payload always carries the same keys, database up or down."""
    response = await client.get("/health")

    assert response.status_code in (200, 503)
    body = response.json()
    assert set(body) == {"status", "app_name", "environment", "version", "database"}
    assert set(body["database"]) == {"status", "latency_ms", "error"}
    assert body["database"]["status"] in ("up", "down")
