"""CORS is open to the future Vite dev server."""

from __future__ import annotations

from httpx import AsyncClient

FRONTEND_ORIGIN = "http://localhost:5173"


async def test_preflight_allows_the_frontend_origin(client: AsyncClient) -> None:
    response = await client.options(
        "/api/v1/health",
        headers={
            "Origin": FRONTEND_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND_ORIGIN


async def test_simple_request_is_annotated_with_cors_headers(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"Origin": FRONTEND_ORIGIN})

    assert response.headers["access-control-allow-origin"] == FRONTEND_ORIGIN
    assert "X-Request-ID" in response.headers["access-control-expose-headers"]


async def test_unknown_origin_is_not_allowed(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"Origin": "http://evil.example"})

    assert "access-control-allow-origin" not in response.headers
