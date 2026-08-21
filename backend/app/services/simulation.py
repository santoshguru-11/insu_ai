"""The guided demo: advance an incident one legal step at a time.

This is a *simulation* of what Sentinel, the diagnosis agent, the planner and
the parts agent would produce — no model is called and no external system is
contacted. What it does not do is shortcut the product's rules: it moves only
along `ALLOWED_TRANSITIONS`, and it stops dead at `approval_required` because
only a human may cross that gate.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.agent_run import AgentRun
from app.models.diagnosis import Diagnosis
from app.models.enums import (
    ActorType,
    AgentKind,
    AgentRunStatus,
    ConfidenceBand,
    PartCheckStatus,
    ProductionImpact,
    ProposalStatus,
    RecommendedAction,
    WorkflowStatus,
)
from app.models.incident import Incident
from app.models.maintenance import MaintenanceProposal, PartCheck
from app.repositories.incident import IncidentRepository
from app.services.workflow import WorkflowService

logger = get_logger(__name__)

#: Reasons a diagnosis is handed to a human instead of straight to approval.
LOW_CONFIDENCE_REASON = (
    "Diagnosis confidence below the auto-approval threshold; competing failure "
    "modes could not be separated from the available evidence."
)
INSUFFICIENT_EVIDENCE_REASON = (
    "Insufficient evidence: the diagnosis cites too few independent signals to "
    "justify an irreversible action."
)

#: A diagnosis needs at least this many evidence items to be actionable.
MINIMUM_EVIDENCE_ITEMS = 2


@dataclass(slots=True)
class SimulationStep:
    previous_state: WorkflowStatus
    next_state: WorkflowStatus
    advanced: bool
    detail: str
    changed_records: dict[str, list[uuid.UUID]] = field(default_factory=dict)
    audit_event_ids: list[uuid.UUID] = field(default_factory=list)


class SimulationService:
    """Drives one incident forward through the simulated agent pipeline."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.incidents = IncidentRepository(session)
        self.workflow = WorkflowService(session)

    async def next_step(
        self,
        incident: Incident,
        *,
        actor_id: str,
        actor_type: ActorType,
        reason: str | None = None,
    ) -> SimulationStep:
        current = incident.workflow_status
        handlers = {
            WorkflowStatus.WATCH: self._escalate,
            WorkflowStatus.ESCALATED: self._diagnose,
            WorkflowStatus.DIAGNOSED: self._route_diagnosis,
            WorkflowStatus.APPROVED: self._dispatch_work_order,
        }
        handler = handlers.get(current)

        if handler is None:
            return self._parked(incident, current)

        # Any step that needs the cloud is refused up front, and the refusal is
        # audited so the trail shows the outage rather than a silent stall.
        if not incident.cloud_available and current in {
            WorkflowStatus.DIAGNOSED,
            WorkflowStatus.APPROVED,
        }:
            await self.workflow.record_blocked_cloud_action(
                incident,
                action=f"simulate_next_step:{current}",
                actor_type=actor_type,
                actor_id=actor_id,
            )
            self.workflow.guard_cloud_available(incident, WorkflowStatus.APPROVAL_REQUIRED)

        return await handler(incident, actor_id=actor_id, actor_type=actor_type, reason=reason)

    # ------------------------------------------------------------- dead ends
    def _parked(self, incident: Incident, current: WorkflowStatus) -> SimulationStep:
        """States the simulation must not move on its own."""
        messages = {
            WorkflowStatus.HUMAN_REVIEW: (
                "Incident is in human review. A person must escalate it to "
                "approval_required; the simulation will not do that for them."
            ),
            WorkflowStatus.APPROVAL_REQUIRED: (
                "Incident is awaiting a human approval decision. Use the approve "
                "or reject endpoint — the simulation cannot cross the approval gate."
            ),
            WorkflowStatus.REJECTED: (
                "Incident was rejected and has already been returned to watch."
            ),
            WorkflowStatus.WORK_ORDER_LIVE: (
                "Work order is live. Capture a technician outcome to resolve it."
            ),
            WorkflowStatus.RESOLVED: "Incident is resolved; the workflow is complete.",
        }
        return SimulationStep(
            previous_state=current,
            next_state=current,
            advanced=False,
            detail=messages.get(current, f"No automatic step is defined from '{current}'."),
        )

    # ----------------------------------------------------------------- steps
    async def _escalate(
        self, incident: Incident, *, actor_id: str, actor_type: ActorType, reason: str | None
    ) -> SimulationStep:
        """Sentinel decides the anomaly has persisted long enough to escalate."""
        anomalies = incident.sentinel_anomalies if "sentinel_anomalies" in incident.__dict__ else []
        run = AgentRun(
            incident_id=incident.id,
            agent_id="sentinel-agent",
            agent_kind=AgentKind.SENTINEL,
            agent_version="1.4.0",
            status=AgentRunStatus.SUCCEEDED,
            confidence=0.99,
            started_at=datetime.now(UTC) - timedelta(seconds=8),
            completed_at=datetime.now(UTC),
        )
        self.session.add(run)
        await self.session.flush()

        result = await self.workflow.transition(
            incident,
            WorkflowStatus.ESCALATED,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason or "Persistent anomaly across analysis windows",
            payload={"agent_run_id": str(run.id), "anomaly_count": len(anomalies)},
        )
        return SimulationStep(
            previous_state=result.previous_state,
            next_state=result.next_state,
            advanced=result.changed,
            detail="Sentinel escalated the persistent anomaly for diagnosis.",
            changed_records={"agent_runs": [run.id]},
            audit_event_ids=result.audit_event_ids,
        )

    async def _diagnose(
        self, incident: Incident, *, actor_id: str, actor_type: ActorType, reason: str | None
    ) -> SimulationStep:
        """Record the diagnosis agent's run and move to `diagnosed`.

        The seeded diagnosis is reused when one already exists, so replaying the
        demo does not stack duplicate diagnoses on an incident.
        """
        changed: dict[str, list[uuid.UUID]] = defaultdict(list)
        diagnosis = await self.incidents.latest_diagnosis(incident.id)

        run = AgentRun(
            incident_id=incident.id,
            agent_id="diagnosis-agent",
            agent_kind=AgentKind.DIAGNOSIS,
            agent_version="2.1.0",
            model_name="simulated-diagnostic-ensemble",
            model_version="2026.05",
            status=AgentRunStatus.SUCCEEDED,
            confidence=diagnosis.confidence if diagnosis else None,
            started_at=datetime.now(UTC) - timedelta(seconds=12),
            completed_at=datetime.now(UTC),
        )
        self.session.add(run)
        await self.session.flush()
        changed["agent_runs"].append(run.id)

        result = await self.workflow.transition(
            incident,
            WorkflowStatus.DIAGNOSED,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason or "Diagnosis agent completed",
            payload={
                "agent_run_id": str(run.id),
                "diagnosis_id": str(diagnosis.id) if diagnosis else None,
                "failure_mode_code": diagnosis.failure_mode_code if diagnosis else None,
                "confidence": diagnosis.confidence if diagnosis else None,
            },
        )
        return SimulationStep(
            previous_state=result.previous_state,
            next_state=result.next_state,
            advanced=result.changed,
            detail="Diagnosis agent completed and attached its findings.",
            changed_records=dict(changed),
            audit_event_ids=result.audit_event_ids,
        )

    async def _route_diagnosis(
        self, incident: Incident, *, actor_id: str, actor_type: ActorType, reason: str | None
    ) -> SimulationStep:
        """Send the diagnosis to a human, or to the approval gate.

        This is the branch the spec defines: low confidence or thin evidence
        goes to `human_review`; anything else with a real recommended action
        goes to `approval_required` — and only after the planner and parts
        agents have produced something to approve.
        """
        diagnosis = await self.incidents.latest_diagnosis(incident.id)
        review_reason = self._human_review_reason(diagnosis)

        if review_reason is not None:
            incident.human_review_reason = review_reason
            result = await self.workflow.transition(
                incident,
                WorkflowStatus.HUMAN_REVIEW,
                actor_type=actor_type,
                actor_id=actor_id,
                reason=review_reason,
                payload={
                    "diagnosis_id": str(diagnosis.id) if diagnosis else None,
                    "confidence": diagnosis.confidence if diagnosis else None,
                    "confidence_band": str(diagnosis.confidence_band) if diagnosis else None,
                    "evidence_count": len(diagnosis.evidence_items) if diagnosis else 0,
                },
            )
            # `transition` clears the reason for non-review states; re-apply it here.
            incident.human_review_reason = review_reason
            await self.session.flush()
            return SimulationStep(
                previous_state=result.previous_state,
                next_state=result.next_state,
                advanced=result.changed,
                detail=f"Routed to human review: {review_reason}",
                audit_event_ids=result.audit_event_ids,
            )

        changed, plan_events = await self._run_planner_and_parts(
            incident, diagnosis, actor_id=actor_id
        )
        result = await self.workflow.transition(
            incident,
            WorkflowStatus.APPROVAL_REQUIRED,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason or "Plan and parts confirmed; awaiting human approval",
            payload={
                "diagnosis_id": str(diagnosis.id) if diagnosis else None,
                "recommended_action": str(diagnosis.recommended_action) if diagnosis else None,
                **{key: [str(v) for v in values] for key, values in changed.items()},
            },
        )
        return SimulationStep(
            previous_state=result.previous_state,
            next_state=result.next_state,
            advanced=result.changed,
            detail=(
                "Planner proposed a window and the parts agent confirmed availability. "
                "Awaiting human approval — nothing has been reserved."
            ),
            changed_records=dict(changed),
            audit_event_ids=[*plan_events, *result.audit_event_ids],
        )

    async def _dispatch_work_order(
        self, incident: Incident, *, actor_id: str, actor_type: ActorType, reason: str | None
    ) -> SimulationStep:
        """`approved` -> `work_order_live`, for an approval that stopped halfway."""
        work_order = await self.incidents.latest_work_order(incident.id)
        result = await self.workflow.transition(
            incident,
            WorkflowStatus.WORK_ORDER_LIVE,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason or "Work order dispatched",
            payload={"work_order_id": str(work_order.id) if work_order else None},
        )
        return SimulationStep(
            previous_state=result.previous_state,
            next_state=result.next_state,
            advanced=result.changed,
            detail="Work order is live with the maintenance crew.",
            audit_event_ids=result.audit_event_ids,
        )

    # ------------------------------------------------------------- internals
    @staticmethod
    def _human_review_reason(diagnosis: Diagnosis | None) -> str | None:
        """Why this diagnosis needs a person, or None if it can go to approval."""
        if diagnosis is None:
            return INSUFFICIENT_EVIDENCE_REASON
        if diagnosis.confidence_band is ConfidenceBand.LOW:
            return LOW_CONFIDENCE_REASON
        if len(diagnosis.evidence_items) < MINIMUM_EVIDENCE_ITEMS:
            return INSUFFICIENT_EVIDENCE_REASON
        if diagnosis.recommended_action is RecommendedAction.MONITOR:
            # Nothing to approve: keep watching rather than raising a gate.
            return "Recommended action is to keep monitoring; no intervention to approve."
        return None

    async def _run_planner_and_parts(
        self, incident: Incident, diagnosis: Diagnosis | None, *, actor_id: str
    ) -> tuple[dict[str, list[uuid.UUID]], list[uuid.UUID]]:
        """Create a proposal and a part check if the seed has not already.

        The part check lands in `checked_not_reserved`: availability is known,
        but nothing is held until a human approves.
        """
        changed: dict[str, list[uuid.UUID]] = defaultdict(list)
        audit_ids: list[uuid.UUID] = []

        proposal = await self.incidents.latest_proposal(incident.id)
        if proposal is None:
            planner_run = AgentRun(
                incident_id=incident.id,
                agent_id="planner-agent",
                agent_kind=AgentKind.PLANNER,
                agent_version="1.2.0",
                status=AgentRunStatus.SUCCEEDED,
                started_at=datetime.now(UTC) - timedelta(seconds=5),
                completed_at=datetime.now(UTC),
            )
            self.session.add(planner_run)
            start = datetime.now(UTC) + timedelta(days=1)
            proposal = MaintenanceProposal(
                incident_id=incident.id,
                proposed_start_at=start,
                proposed_end_at=start + timedelta(hours=6),
                duration_hours=6.0,
                rul_margin_days=((diagnosis.rul_estimate_days or 0) - 9 if diagnosis else None),
                production_impact=ProductionImpact.NONE,
                crew_available=True,
                planned_changeover=True,
                status=ProposalStatus.PROPOSED,
            )
            self.session.add(proposal)
            await self.session.flush()
            changed["agent_runs"].append(planner_run.id)
            changed["maintenance_proposals"].append(proposal.id)

        if not proposal.part_checks:
            parts_run = AgentRun(
                incident_id=incident.id,
                agent_id="parts-agent",
                agent_kind=AgentKind.PARTS,
                agent_version="1.0.3",
                status=AgentRunStatus.SUCCEEDED,
                started_at=datetime.now(UTC) - timedelta(seconds=3),
                completed_at=datetime.now(UTC),
            )
            self.session.add(parts_run)
            part_check = PartCheck(
                maintenance_proposal_id=proposal.id,
                sku="BRG-6220-C3",
                quantity=1,
                in_stock=True,
                location="STORE-A",
                lead_time_days=0,
                estimated_cost=840,
                currency="INR",
                status=PartCheckStatus.CHECKED_NOT_RESERVED,
            )
            self.session.add(part_check)
            await self.session.flush()
            changed["agent_runs"].append(parts_run.id)
            changed["part_checks"].append(part_check.id)

        return changed, audit_ids
