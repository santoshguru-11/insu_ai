"""WebSocket event contract.

Every message pushed to a subscribed console uses this envelope, so a client
can switch on `event_type` and read the payload without guessing at shape.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class WebSocketEventType(StrEnum):
    """Names broadcast on the incident channel."""

    SNAPSHOT = "incident.snapshot"
    INCIDENT_UPDATED = "incident.updated"
    APPROVAL_CREATED = "approval.created"
    APPROVAL_REJECTED = "approval.rejected"
    PART_RESERVED = "part.reserved"
    WORK_ORDER_CREATED = "work_order.created"
    OUTCOME_CAPTURED = "outcome.captured"


class WebSocketEvent(BaseModel):
    event_type: WebSocketEventType
    incident_id: uuid.UUID
    trace_id: str = Field(examples=["tr_9f21"])
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data: dict[str, Any] = Field(default_factory=dict)
