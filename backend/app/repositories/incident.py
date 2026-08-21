"""Incident persistence."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select

from app.models.enums import WorkflowStatus
from app.models.incident import Incident
from app.repositories.base import BaseRepository


class IncidentRepository(BaseRepository[Incident]):
    model = Incident

    async def get_by_trace_id(self, trace_id: str) -> Incident | None:
        result = await self.session.execute(select(Incident).where(Incident.trace_id == trace_id))
        return result.scalar_one_or_none()

    async def list_by_status(
        self, status: WorkflowStatus, *, limit: int = 100, offset: int = 0
    ) -> Sequence[Incident]:
        result = await self.session.execute(
            select(Incident)
            .where(Incident.workflow_status == status)
            .order_by(Incident.detected_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def list_for_asset(
        self, asset_id: uuid.UUID, *, limit: int = 100, offset: int = 0
    ) -> Sequence[Incident]:
        result = await self.session.execute(
            select(Incident)
            .where(Incident.asset_id == asset_id)
            .order_by(Incident.detected_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()
