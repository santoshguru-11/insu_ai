"""Audit-event contracts.

There is deliberately no update schema: `audit_events` is append-only.
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
    trace_id: str = Field(examples=["tr_9f21"])
    incident_id: uuid.UUID | None = None
    actor_type: ActorType
    actor_id: str | None = None
    event_type: str = Field(examples=["workflow.transitioned"])
    event_payload_json: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Transition events carry previous_state, next_state, reason and any "
            "records the step created."
        ),
    )
    occurred_at: datetime
