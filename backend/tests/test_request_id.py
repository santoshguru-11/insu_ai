"""Request-id middleware behaviour."""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def test_response_carries_a_generated_request_id(client: AsyncClient) -> None:
    response = await client.get("/health")

    request_id = response.headers.get("X-Request-ID")
    assert request_id, "X-Request-ID header is missing"
    # A generated id must be a well-formed UUID.
    uuid.UUID(request_id)


async def test_incoming_request_id_is_preserved(client: AsyncClient) -> None:
    supplied = "trace-from-the-caller-0001"

    response = await client.get("/health", headers={"X-Request-ID": supplied})

    assert response.headers["X-Request-ID"] == supplied


async def test_each_request_gets_a_distinct_id(client: AsyncClient) -> None:
    first = await client.get("/health")
    second = await client.get("/health")

    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]


async def test_error_envelope_includes_the_request_id(client: AsyncClient) -> None:
    supplied = str(uuid.uuid4())

    response = await client.get("/no-such-route", headers={"X-Request-ID": supplied})

    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id", "details"}
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["request_id"] == supplied
    assert response.headers["X-Request-ID"] == supplied
