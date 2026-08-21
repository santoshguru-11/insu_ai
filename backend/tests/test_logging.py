"""Structured access logs carry the fields operators query on."""

from __future__ import annotations

import json
import logging

from httpx import AsyncClient

from app.core.logging import configure_logging


async def test_access_log_is_json_with_required_fields(client: AsyncClient, capsys) -> None:
    configure_logging("INFO")
    logging.getLogger().setLevel(logging.INFO)

    request_id = "log-check-0001"
    await client.get("/health", headers={"X-Request-ID": request_id})

    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    records = [json.loads(line) for line in lines if line.lstrip().startswith("{")]
    access_logs = [r for r in records if r.get("event") == "http_request"]

    assert access_logs, f"no http_request log line found in: {lines}"
    entry = access_logs[-1]

    assert entry["timestamp"]
    assert entry["level"] == "info"
    assert entry["request_id"] == request_id
    assert entry["method"] == "GET"
    assert entry["route"] == "/health"
    assert entry["status_code"] in (200, 503)
    assert isinstance(entry["duration_ms"], (int, float))
