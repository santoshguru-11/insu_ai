"""Audit-event schemas.

There is deliberately no `AuditEventUpdate`: the table is append-only.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import ActorType
from app.schemas.common import ORMModel


class AuditEventCreate(BaseModel):
    trace_id: str = Field(max_length=64)
    incident_id: uuid.UUID | None = None
    actor_type: ActorType
    actor_id: str | None = Field(default=None, max_length=128)
    event_type: str = Field(max_length=128)
    event_payload_json: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None


class AuditEventRead(ORMModel):
    id: uuid.UUID
    trace_id: str
    incident_id: uuid.UUID | None
    actor_type: ActorType
    actor_id: str | None
    event_type: str
    event_payload_json: dict[str, Any]
    occurred_at: datetime
