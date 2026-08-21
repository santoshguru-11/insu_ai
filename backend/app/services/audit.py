"""Audit-trail service.

Every state change in the workflow should land here. The service exposes a
single `record` entry point — there is no update or delete counterpart.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent
from app.models.enums import ActorType
from app.repositories.audit_event import AuditEventRepository


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = AuditEventRepository(session)

    async def record(
        self,
        *,
        trace_id: str,
        event_type: str,
        actor_type: ActorType,
        actor_id: str | None = None,
        incident_id: uuid.UUID | None = None,
        payload: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            trace_id=trace_id,
            incident_id=incident_id,
            actor_type=actor_type,
            actor_id=actor_id,
            event_type=event_type,
            event_payload_json=payload or {},
            occurred_at=occurred_at or datetime.now(UTC),
        )
        return await self.repository.append(event)

    async def timeline(self, trace_id: str) -> Sequence[AuditEvent]:
        return await self.repository.list_by_trace_id(trace_id)
