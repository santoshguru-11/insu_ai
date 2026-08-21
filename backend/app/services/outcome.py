"""Technician outcome capture — the feedback loop that closes an incident."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.models.enums import ActorType, WorkflowStatus, WorkOrderStatus
from app.models.incident import Incident
from app.models.work_order import TechnicianOutcome, WorkOrder
from app.repositories.incident import IncidentRepository
from app.schemas.maintenance import TechnicianOutcomeCreate
from app.services.audit import AuditService
from app.services.workflow import WorkflowService

OUTCOME_CAPTURED_EVENT = "outcome.captured"


@dataclass(slots=True)
class OutcomeResult:
    outcome: TechnicianOutcome
    work_order: WorkOrder
    audit_event_ids: list[uuid.UUID] = field(default_factory=list)


class OutcomeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.incidents = IncidentRepository(session)
        self.workflow = WorkflowService(session)
        self.audit = AuditService(session)

    async def capture(self, incident: Incident, request: TechnicianOutcomeCreate) -> OutcomeResult:
        """Record what the technician found, complete the order, resolve the incident."""
        if incident.workflow_status is not WorkflowStatus.WORK_ORDER_LIVE:
            raise ConflictError(
                (
                    f"Incident is in '{incident.workflow_status}'; an outcome can only be "
                    f"captured while a work order is live."
                ),
                code="WORK_ORDER_NOT_LIVE",
                details={
                    "incident_id": str(incident.id),
                    "trace_id": incident.trace_id,
                    "current_state": str(incident.workflow_status),
                    "required_state": str(WorkflowStatus.WORK_ORDER_LIVE),
                },
            )

        work_order = await self.incidents.latest_work_order(incident.id)
        if work_order is None:
            raise ConflictError(
                "Incident has no work order to report against.",
                code="WORK_ORDER_MISSING",
                details={"incident_id": str(incident.id)},
            )

        captured_at = datetime.now(UTC)
        outcome = TechnicianOutcome(
            work_order_id=work_order.id,
            technician_id=request.technician_id,
            technician_name=request.technician_name,
            diagnosis_confirmed=request.diagnosis_confirmed,
            actual_finding=request.actual_finding,
            # Stored as a JSON list of SKUs; richer part records can slot in later.
            parts_used_json=list(request.parts_used),
            technician_note=request.technician_note,
            repair_duration_hours=request.repair_duration_hours,
            captured_at=captured_at,
        )
        self.session.add(outcome)
        work_order.status = WorkOrderStatus.COMPLETED
        work_order.completed_at = captured_at
        await self.session.flush()

        audit_ids: list[uuid.UUID] = []
        event = await self.audit.record(
            trace_id=incident.trace_id,
            event_type=OUTCOME_CAPTURED_EVENT,
            actor_type=ActorType.HUMAN,
            actor_id=request.technician_id,
            incident_id=incident.id,
            occurred_at=captured_at,
            payload={
                "technician_outcome_id": str(outcome.id),
                "work_order_id": str(work_order.id),
                "work_order_reference": work_order.external_reference,
                "technician_name": request.technician_name,
                "diagnosis_confirmed": request.diagnosis_confirmed,
                "actual_finding": request.actual_finding,
                "parts_used": list(request.parts_used),
                "repair_duration_hours": request.repair_duration_hours,
            },
        )
        audit_ids.append(event.id)

        resolved = await self.workflow.transition(
            incident,
            WorkflowStatus.RESOLVED,
            actor_type=ActorType.HUMAN,
            actor_id=request.technician_id,
            reason=request.technician_note or "Technician outcome captured",
            payload={
                "technician_outcome_id": str(outcome.id),
                "diagnosis_confirmed": request.diagnosis_confirmed,
            },
        )
        audit_ids.extend(resolved.audit_event_ids)

        return OutcomeResult(outcome=outcome, work_order=work_order, audit_event_ids=audit_ids)
