"""The human approval gate, and the irreversible work it unlocks.

Product rule enforced here: nothing irreversible — part reservation or
work-order creation — happens before a valid approval decision exists. The
ordering below is deliberate and must not be rearranged:

    validate state -> validate cloud -> record decision -> transition to
    approved -> reserve parts -> create work order -> transition to
    work_order_live

Each of those steps writes its own audit event, so the trail shows the approval
strictly preceding the actions it authorised.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ApprovalStateError, ConflictError
from app.core.logging import get_logger
from app.models.approval import ApprovalDecision
from app.models.enums import (
    ActorType,
    ApprovalDecisionType,
    PartCheckStatus,
    ProposalStatus,
    WorkflowStatus,
    WorkOrderStatus,
)
from app.models.incident import Incident
from app.models.work_order import WorkOrder
from app.repositories.incident import IncidentRepository
from app.schemas.approval import ApprovalRequest, ApprovalTokenRead
from app.services import tokens
from app.services.audit import AuditService
from app.services.workflow import WorkflowService

logger = get_logger(__name__)

#: The simulated CMMS reference handed back for an approved incident. A real
#: deployment would take this from the CMMS create-work-order response.
SIMULATED_WORK_ORDER_REFERENCE = "WO-40219"

APPROVAL_CREATED_EVENT = "approval.created"
APPROVAL_REJECTED_EVENT = "approval.rejected"
PART_RESERVED_EVENT = "part.reserved"
WORK_ORDER_CREATED_EVENT = "work_order.created"


@dataclass(slots=True)
class ApprovalOutcome:
    decision: ApprovalDecision
    token: ApprovalTokenRead
    work_order: WorkOrder | None = None
    work_order_reference: str | None = None
    audit_event_ids: list[uuid.UUID] = field(default_factory=list)
    reserved_part_check_ids: list[uuid.UUID] = field(default_factory=list)


@dataclass(slots=True)
class RejectionOutcome:
    decision: ApprovalDecision
    audit_event_ids: list[uuid.UUID] = field(default_factory=list)


class ApprovalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.incidents = IncidentRepository(session)
        self.workflow = WorkflowService(session)
        self.audit = AuditService(session)

    # ------------------------------------------------------------- guardrails
    def _require_approval_state(self, incident: Incident) -> None:
        if incident.workflow_status is not WorkflowStatus.APPROVAL_REQUIRED:
            raise ApprovalStateError(
                (
                    f"Incident is in '{incident.workflow_status}'; an approval decision "
                    f"is only accepted in '{WorkflowStatus.APPROVAL_REQUIRED}'."
                ),
                details={
                    "incident_id": str(incident.id),
                    "trace_id": incident.trace_id,
                    "current_state": str(incident.workflow_status),
                    "required_state": str(WorkflowStatus.APPROVAL_REQUIRED),
                },
            )

    async def _require_proposal(self, incident: Incident):
        proposal = await self.incidents.latest_proposal(incident.id)
        if proposal is None:
            raise ConflictError(
                "Incident has no maintenance proposal to decide on.",
                code="PROPOSAL_MISSING",
                details={"incident_id": str(incident.id), "trace_id": incident.trace_id},
            )
        return proposal

    # ---------------------------------------------------------------- approve
    async def approve(self, incident: Incident, request: ApprovalRequest) -> ApprovalOutcome:
        """Approve the proposal, then perform the work it authorises."""
        # Cloud availability is checked first: when the link is down the whole
        # approval subsystem is unreachable, which is a more useful thing to tell
        # the operator than "wrong state" for an incident that cannot reach the
        # right state either.
        if not incident.cloud_available:
            await self.workflow.record_blocked_cloud_action(
                incident,
                action="approve",
                actor_type=ActorType.HUMAN,
                actor_id=request.approver_id,
            )
            self.workflow.guard_cloud_available(incident)

        self._require_approval_state(incident)
        proposal = await self._require_proposal(incident)
        decided_at = datetime.now(UTC)
        scoped = tokens.issue(incident.id, action="approve")

        decision = ApprovalDecision(
            incident_id=incident.id,
            proposal_id=proposal.id,
            decision=ApprovalDecisionType.APPROVED,
            approver_id=request.approver_id,
            approver_name=request.approver_name,
            reason=request.reason,
            token_id=scoped.token_id,
            token_hash=scoped.token_hash,
            token_expires_at=scoped.expires_at,
            decided_at=decided_at,
        )
        self.session.add(decision)
        proposal.status = ProposalStatus.APPROVED
        await self.session.flush()

        audit_ids: list[uuid.UUID] = []
        approval_event = await self.audit.record(
            trace_id=incident.trace_id,
            event_type=APPROVAL_CREATED_EVENT,
            actor_type=ActorType.HUMAN,
            actor_id=request.approver_id,
            incident_id=incident.id,
            occurred_at=decided_at,
            payload={
                "decision": str(ApprovalDecisionType.APPROVED),
                "approval_decision_id": str(decision.id),
                "proposal_id": str(proposal.id),
                "approver_name": request.approver_name,
                "reason": request.reason,
                # Token metadata only — the secret is never written to the trail.
                "token_id": str(scoped.token_id),
                "token_scope": scoped.scope,
                "token_expires_at": scoped.expires_at.isoformat(),
            },
        )
        audit_ids.append(approval_event.id)

        # The approval now exists; moving out of approval_required is what makes
        # the irreversible steps below legal.
        approved = await self.workflow.transition(
            incident,
            WorkflowStatus.APPROVED,
            actor_type=ActorType.HUMAN,
            actor_id=request.approver_id,
            reason=request.reason,
            payload={"approval_decision_id": str(decision.id)},
        )
        audit_ids.extend(approved.audit_event_ids)

        reserved_ids, reservation_events = await self._reserve_parts(
            incident, proposal, decision, actor_id=request.approver_id
        )
        audit_ids.extend(reservation_events)

        work_order, work_order_event = await self._create_work_order(
            incident, decision, actor_id=request.approver_id
        )
        audit_ids.append(work_order_event)

        live = await self.workflow.transition(
            incident,
            WorkflowStatus.WORK_ORDER_LIVE,
            actor_type=ActorType.SYSTEM,
            actor_id=request.approver_id,
            reason="Work order dispatched",
            payload={
                "work_order_id": str(work_order.id),
                "work_order_reference": work_order.external_reference,
            },
        )
        audit_ids.extend(live.audit_event_ids)

        # The token covered this one operation; mark it spent so it cannot be replayed.
        decision.used_at = datetime.now(UTC)
        await self.session.flush()

        return ApprovalOutcome(
            decision=decision,
            token=ApprovalTokenRead(
                token_id=scoped.token_id,
                expires_at=scoped.expires_at,
                scope=scoped.scope,
            ),
            work_order=work_order,
            work_order_reference=work_order.external_reference,
            audit_event_ids=audit_ids,
            reserved_part_check_ids=reserved_ids,
        )

    # ----------------------------------------------------------------- reject
    async def reject(self, incident: Incident, request: ApprovalRequest) -> RejectionOutcome:
        """Reject the proposal and put the asset back under watch.

        Nothing is reserved and no work order is created — the rejection path
        never touches the irreversible helpers.
        """
        self._require_approval_state(incident)
        proposal = await self._require_proposal(incident)
        decided_at = datetime.now(UTC)

        decision = ApprovalDecision(
            incident_id=incident.id,
            proposal_id=proposal.id,
            decision=ApprovalDecisionType.REJECTED,
            approver_id=request.approver_id,
            approver_name=request.approver_name,
            reason=request.reason,
            decided_at=decided_at,
        )
        self.session.add(decision)
        proposal.status = ProposalStatus.REJECTED
        await self.session.flush()

        audit_ids: list[uuid.UUID] = []
        rejection_event = await self.audit.record(
            trace_id=incident.trace_id,
            event_type=APPROVAL_REJECTED_EVENT,
            actor_type=ActorType.HUMAN,
            actor_id=request.approver_id,
            incident_id=incident.id,
            occurred_at=decided_at,
            payload={
                "decision": str(ApprovalDecisionType.REJECTED),
                "approval_decision_id": str(decision.id),
                "proposal_id": str(proposal.id),
                "approver_name": request.approver_name,
                "reason": request.reason,
                "reservation_created": False,
                "work_order_created": False,
            },
        )
        audit_ids.append(rejection_event.id)

        rejected = await self.workflow.transition(
            incident,
            WorkflowStatus.REJECTED,
            actor_type=ActorType.HUMAN,
            actor_id=request.approver_id,
            reason=request.reason,
            payload={"approval_decision_id": str(decision.id)},
        )
        audit_ids.extend(rejected.audit_event_ids)

        # Returning to watch is its own audited transition, not a side effect.
        back_to_watch = await self.workflow.transition(
            incident,
            WorkflowStatus.WATCH,
            actor_type=ActorType.SYSTEM,
            actor_id=request.approver_id,
            reason="Proposal rejected; asset returned to sentinel watch",
            payload={"approval_decision_id": str(decision.id)},
        )
        audit_ids.extend(back_to_watch.audit_event_ids)

        return RejectionOutcome(decision=decision, audit_event_ids=audit_ids)

    # ------------------------------------------------ irreversible operations
    async def _reserve_parts(
        self,
        incident: Incident,
        proposal,
        decision: ApprovalDecision,
        *,
        actor_id: str | None,
    ) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
        """Simulate holding stock. Only ever called after an approval exists."""
        if decision.decision is not ApprovalDecisionType.APPROVED:
            raise ConflictError(
                "Parts cannot be reserved without an approved decision.",
                code="APPROVAL_REQUIRED_FOR_RESERVATION",
            )
        self.workflow.guard_cloud_available(incident)

        reserved_at = datetime.now(UTC)
        reserved_ids: list[uuid.UUID] = []
        audit_ids: list[uuid.UUID] = []
        for part_check in proposal.part_checks:
            if part_check.status is PartCheckStatus.RESERVED:
                continue  # already held; re-running must not double-reserve
            part_check.status = PartCheckStatus.RESERVED
            part_check.reserved_at = reserved_at
            reserved_ids.append(part_check.id)
        await self.session.flush()

        if reserved_ids:
            event = await self.audit.record(
                trace_id=incident.trace_id,
                event_type=PART_RESERVED_EVENT,
                actor_type=ActorType.SYSTEM,
                actor_id=actor_id,
                incident_id=incident.id,
                occurred_at=reserved_at,
                payload={
                    "approval_decision_id": str(decision.id),
                    "part_check_ids": [str(pk) for pk in reserved_ids],
                    "skus": [check.sku for check in proposal.part_checks],
                    "simulated": True,
                },
            )
            audit_ids.append(event.id)
        return reserved_ids, audit_ids

    async def _create_work_order(
        self, incident: Incident, decision: ApprovalDecision, *, actor_id: str | None
    ) -> tuple[WorkOrder, uuid.UUID]:
        """Simulate the CMMS create-work-order call. Approval-gated."""
        if decision.decision is not ApprovalDecisionType.APPROVED:
            raise ConflictError(
                "A work order cannot be created without an approved decision.",
                code="APPROVAL_REQUIRED_FOR_WORK_ORDER",
            )
        self.workflow.guard_cloud_available(incident)

        existing = await self.incidents.latest_work_order(incident.id)
        if existing is not None and existing.status is not WorkOrderStatus.CANCELLED:
            # Idempotent: a retried approval reuses the order it already created.
            work_order = existing
        else:
            work_order = WorkOrder(
                incident_id=incident.id,
                external_reference=SIMULATED_WORK_ORDER_REFERENCE,
                status=WorkOrderStatus.OPEN,
                created_by=actor_id,
            )
            self.session.add(work_order)
            await self.session.flush()

        event = await self.audit.record(
            trace_id=incident.trace_id,
            event_type=WORK_ORDER_CREATED_EVENT,
            actor_type=ActorType.SYSTEM,
            actor_id=actor_id,
            incident_id=incident.id,
            payload={
                "approval_decision_id": str(decision.id),
                "work_order_id": str(work_order.id),
                "work_order_reference": work_order.external_reference,
                "simulated": True,
            },
        )
        return work_order, event.id
