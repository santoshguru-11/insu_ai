"""Incident persistence, including the eager loads the detail view needs."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import selectinload

from app.models.agent_run import AgentRun
from app.models.approval import ApprovalDecision
from app.models.diagnosis import Diagnosis
from app.models.enums import ScenarioType, Severity, WorkflowStatus
from app.models.incident import Incident
from app.models.maintenance import MaintenanceProposal
from app.models.work_order import WorkOrder
from app.repositories.base import BaseRepository


class IncidentRepository(BaseRepository[Incident]):
    model = Incident

    # ---------------------------------------------------------------- lookups
    async def get_by_trace_id(self, trace_id: str) -> Incident | None:
        result = await self.session.execute(select(Incident).where(Incident.trace_id == trace_id))
        return result.scalar_one_or_none()

    async def get_with_detail(self, incident_id: uuid.UUID) -> Incident | None:
        """Load an incident and every child record the detail endpoint renders.

        One round trip per collection via `selectinload`, rather than a join
        fan-out that would multiply rows across five one-to-many relationships.
        """
        result = await self.session.execute(
            select(Incident)
            .where(Incident.id == incident_id)
            .options(
                selectinload(Incident.asset),
                selectinload(Incident.sentinel_anomalies),
                selectinload(Incident.agent_runs),
                selectinload(Incident.diagnoses).selectinload(Diagnosis.evidence_items),
                selectinload(Incident.diagnoses).selectinload(Diagnosis.alternatives),
                selectinload(Incident.maintenance_proposals).selectinload(
                    MaintenanceProposal.part_checks
                ),
                selectinload(Incident.approval_decisions),
                selectinload(Incident.work_orders).selectinload(WorkOrder.technician_outcomes),
            )
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------ lists
    def _filtered(
        self,
        *,
        workflow_status: WorkflowStatus | None = None,
        severity: Severity | None = None,
        asset_id: uuid.UUID | None = None,
        scenario_type: ScenarioType | None = None,
    ) -> Select[tuple[Incident]]:
        stmt = select(Incident)
        if workflow_status is not None:
            stmt = stmt.where(Incident.workflow_status == workflow_status)
        if severity is not None:
            stmt = stmt.where(Incident.severity == severity)
        if asset_id is not None:
            stmt = stmt.where(Incident.asset_id == asset_id)
        if scenario_type is not None:
            stmt = stmt.where(Incident.scenario_type == scenario_type)
        return stmt

    async def list_filtered(
        self,
        *,
        workflow_status: WorkflowStatus | None = None,
        severity: Severity | None = None,
        asset_id: uuid.UUID | None = None,
        scenario_type: ScenarioType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Incident]:
        stmt = (
            self._filtered(
                workflow_status=workflow_status,
                severity=severity,
                asset_id=asset_id,
                scenario_type=scenario_type,
            )
            .options(
                selectinload(Incident.asset),
                selectinload(Incident.diagnoses),
            )
            .order_by(Incident.detected_at.desc(), Incident.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_filtered(
        self,
        *,
        workflow_status: WorkflowStatus | None = None,
        severity: Severity | None = None,
        asset_id: uuid.UUID | None = None,
        scenario_type: ScenarioType | None = None,
    ) -> int:
        stmt = self._filtered(
            workflow_status=workflow_status,
            severity=severity,
            asset_id=asset_id,
            scenario_type=scenario_type,
        ).with_only_columns(func.count(Incident.id))
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def count_open_for_asset(self, asset_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count(Incident.id)).where(
                Incident.asset_id == asset_id,
                Incident.workflow_status != WorkflowStatus.RESOLVED,
            )
        )
        return int(result.scalar_one())

    async def latest_for_asset(self, asset_id: uuid.UUID) -> Incident | None:
        result = await self.session.execute(
            select(Incident)
            .where(Incident.asset_id == asset_id)
            .order_by(Incident.detected_at.desc(), Incident.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    # --------------------------------------------------------- child lookups
    async def latest_diagnosis(self, incident_id: uuid.UUID) -> Diagnosis | None:
        result = await self.session.execute(
            select(Diagnosis)
            .where(Diagnosis.incident_id == incident_id)
            .options(
                selectinload(Diagnosis.evidence_items),
                selectinload(Diagnosis.alternatives),
            )
            .order_by(Diagnosis.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def latest_proposal(self, incident_id: uuid.UUID) -> MaintenanceProposal | None:
        result = await self.session.execute(
            select(MaintenanceProposal)
            .where(MaintenanceProposal.incident_id == incident_id)
            .options(selectinload(MaintenanceProposal.part_checks))
            .order_by(MaintenanceProposal.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def latest_approval(self, incident_id: uuid.UUID) -> ApprovalDecision | None:
        result = await self.session.execute(
            select(ApprovalDecision)
            .where(ApprovalDecision.incident_id == incident_id)
            .order_by(ApprovalDecision.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def latest_work_order(self, incident_id: uuid.UUID) -> WorkOrder | None:
        result = await self.session.execute(
            select(WorkOrder)
            .where(WorkOrder.incident_id == incident_id)
            .options(selectinload(WorkOrder.technician_outcomes))
            .order_by(WorkOrder.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def latest_agent_run(self, incident_id: uuid.UUID) -> AgentRun | None:
        result = await self.session.execute(
            select(AgentRun)
            .where(AgentRun.incident_id == incident_id)
            .order_by(AgentRun.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
