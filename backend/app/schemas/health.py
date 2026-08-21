"""Schemas for the health endpoint."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DatabaseHealth(BaseModel):
    status: Literal["up", "down"]
    latency_ms: float | None = Field(
        default=None, description="Round-trip time of the `SELECT 1` probe."
    )
    error: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    app_name: str
    environment: str
    version: str
    database: DatabaseHealth
