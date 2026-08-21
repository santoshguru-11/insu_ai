"""Audit-event persistence — append and read only.

This class intentionally extends `ReadOnlyRepository` rather than
`BaseRepository`, so `update`, `delete` and `delete_by_id` simply do not exist
on it. The database trigger installed by the initial migration is the second
line of defence.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select

from app.models.audit import AuditEvent
from app.repositories.base import ReadOnlyRepository


class AuditEventRepository(ReadOnlyRepository[AuditEvent]):
    model = AuditEvent

    async def append(self, event: AuditEvent) -> AuditEvent:
        """The only write path into the audit trail."""
        return await self.add(event)

    async def list_by_trace_id(
        self, trace_id: str, *, limit: int = 200, offset: int = 0
    ) -> Sequence[AuditEvent]:
        result = await self.session.execute(
            select(AuditEvent)
            .where(AuditEvent.trace_id == trace_id)
            .order_by(AuditEvent.occurred_at.asc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def count_by_incident(self, incident_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count(AuditEvent.id)).where(AuditEvent.incident_id == incident_id)
        )
        return int(result.scalar_one())

    async def list_by_incident(
        self, incident_id: uuid.UUID, *, limit: int = 200, offset: int = 0
    ) -> Sequence[AuditEvent]:
        result = await self.session.execute(
            select(AuditEvent)
            .where(AuditEvent.incident_id == incident_id)
            .order_by(AuditEvent.occurred_at.asc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()
