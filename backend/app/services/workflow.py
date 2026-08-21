"""The incident state machine.

Every workflow state change in the product goes through `WorkflowService`.
Route handlers never assign `incident.workflow_status` themselves — that keeps
one place responsible for validating the move, writing the audit event, and
notifying subscribed consoles.

Two rules hold everywhere:

* a transition that is not in `ALLOWED_TRANSITIONS` is refused, and
* no irreversible action (part reservation, work-order creation) may run before
  an approval decision has moved the incident out of `approval_required`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CloudUnavailableError, InvalidTransitionError
from app.core.logging import get_logger
from app.db.session import get_session_factory
from app.models.enums import ActorType, WorkflowStatus
from app.models.incident import Incident
from app.services.audit import AuditService

logger = get_logger(__name__)

WORKFLOW_TRANSITION_EVENT = "workflow.transitioned"
CLOUD_ACTION_BLOCKED_EVENT = "cloud.action_blocked"

#: The only moves the product permits. Anything else is a bug or a bad request.
ALLOWED_TRANSITIONS: dict[WorkflowStatus, frozenset[WorkflowStatus]] = {
    WorkflowStatus.WATCH: frozenset({WorkflowStatus.ESCALATED}),
    WorkflowStatus.ESCALATED: frozenset({WorkflowStatus.DIAGNOSED}),
    # A diagnosis either needs a human (low confidence / thin evidence) or is
    # solid enough to ask for approval.
    WorkflowStatus.DIAGNOSED: frozenset(
        {WorkflowStatus.HUMAN_REVIEW, WorkflowStatus.APPROVAL_REQUIRED}
    ),
    WorkflowStatus.HUMAN_REVIEW: frozenset({WorkflowStatus.APPROVAL_REQUIRED}),
    WorkflowStatus.APPROVAL_REQUIRED: frozenset({WorkflowStatus.APPROVED, WorkflowStatus.REJECTED}),
    WorkflowStatus.APPROVED: frozenset({WorkflowStatus.WORK_ORDER_LIVE}),
    WorkflowStatus.WORK_ORDER_LIVE: frozenset({WorkflowStatus.RESOLVED}),
    # A rejected proposal does not end the incident: the asset goes back under
    # watch so the sentinel can re-escalate it later.
    WorkflowStatus.REJECTED: frozenset({WorkflowStatus.WATCH}),
    WorkflowStatus.RESOLVED: frozenset(),
}

#: States from which no further automatic progress is possible.
TERMINAL_STATES: frozenset[WorkflowStatus] = frozenset({WorkflowStatus.RESOLVED})

#: Reaching any of these requires a cloud round trip in the real product.
CLOUD_DEPENDENT_STATES: frozenset[WorkflowStatus] = frozenset(
    {
        WorkflowStatus.APPROVAL_REQUIRED,
        WorkflowStatus.APPROVED,
        WorkflowStatus.WORK_ORDER_LIVE,
    }
)


@dataclass(slots=True)
class TransitionResult:
    """What a transition attempt did."""

    incident: Incident
    previous_state: WorkflowStatus
    next_state: WorkflowStatus
    #: False when the incident was already in `next_state` and nothing changed.
    changed: bool
    audit_event_ids: list[uuid.UUID] = field(default_factory=list)


def can_transition(current: WorkflowStatus, target: WorkflowStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def next_states(current: WorkflowStatus) -> frozenset[WorkflowStatus]:
    return ALLOWED_TRANSITIONS.get(current, frozenset())


class WorkflowService:
    """Validates and records incident state changes."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditService(session)

    async def transition(
        self,
        incident: Incident,
        target: WorkflowStatus,
        *,
        actor_type: ActorType,
        actor_id: str | None = None,
        reason: str | None = None,
        payload: dict[str, Any] | None = None,
        event_type: str = WORKFLOW_TRANSITION_EVENT,
    ) -> TransitionResult:
        """Move `incident` to `target`, or explain why that is not allowed.

        Idempotent: asking for the state the incident is already in is a no-op
        that writes no audit event, so a retried request cannot double-record a
        transition.
        """
        current = incident.workflow_status

        if current == target:
            logger.info(
                "workflow_transition_noop",
                incident_id=str(incident.id),
                trace_id=incident.trace_id,
                state=str(target),
            )
            return TransitionResult(
                incident=incident,
                previous_state=current,
                next_state=target,
                changed=False,
            )

        if not can_transition(current, target):
            raise InvalidTransitionError(
                f"Cannot move incident from '{current}' to '{target}'.",
                details={
                    "incident_id": str(incident.id),
                    "trace_id": incident.trace_id,
                    "current_state": str(current),
                    "requested_state": str(target),
                    "allowed_next_states": sorted(str(s) for s in next_states(current)),
                },
            )

        self.guard_cloud_available(incident, target)

        occurred_at = datetime.now(UTC)
        incident.workflow_status = target
        if target == WorkflowStatus.RESOLVED and incident.resolved_at is None:
            incident.resolved_at = occurred_at
        if target != WorkflowStatus.HUMAN_REVIEW:
            # The reason only describes the review the incident is in right now.
            incident.human_review_reason = None

        event = await self.audit.record(
            trace_id=incident.trace_id,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            incident_id=incident.id,
            occurred_at=occurred_at,
            payload={
                "previous_state": str(current),
                "next_state": str(target),
                "reason": reason,
                **(payload or {}),
            },
        )
        await self.session.flush()

        logger.info(
            "workflow_transitioned",
            incident_id=str(incident.id),
            trace_id=incident.trace_id,
            previous_state=str(current),
            next_state=str(target),
            actor_type=str(actor_type),
            actor_id=actor_id,
        )
        return TransitionResult(
            incident=incident,
            previous_state=current,
            next_state=target,
            changed=True,
            audit_event_ids=[event.id],
        )

    def guard_cloud_available(
        self, incident: Incident, target: WorkflowStatus | None = None
    ) -> None:
        """Refuse cloud-dependent work while the incident's link is simulated down.

        Passing `target=None` guards an action (approve, reserve, create work
        order) rather than a state change.
        """
        if incident.cloud_available:
            return
        if target is not None and target not in CLOUD_DEPENDENT_STATES:
            return
        raise CloudUnavailableError(
            details={
                "incident_id": str(incident.id),
                "trace_id": incident.trace_id,
                "requested_state": str(target) if target else None,
                "edge_diagnosis_available": True,
            }
        )

    async def record_blocked_cloud_action(
        self,
        incident: Incident,
        *,
        action: str,
        actor_type: ActorType,
        actor_id: str | None,
        reason: str | None = None,
    ) -> uuid.UUID:
        """Audit a cloud action that was refused, so the outage is visible in the trail.

        Written on its own session and committed immediately. The request that
        triggered this is about to fail with `CLOUD_UNAVAILABLE`, which rolls the
        request transaction back — and the whole point of the record is that the
        refusal is still visible afterwards. Auditing a rejected action is not
        part of the rejected action's transaction.
        """
        payload = {
            "action": action,
            "reason": reason or "cloud_unavailable",
            "workflow_status": str(incident.workflow_status),
            "edge_diagnosis_preserved": True,
        }
        incident_id = incident.id
        trace_id = incident.trace_id

        async with get_session_factory()() as session:
            event = await AuditService(session).record(
                trace_id=trace_id,
                event_type=CLOUD_ACTION_BLOCKED_EVENT,
                actor_type=actor_type,
                actor_id=actor_id,
                incident_id=incident_id,
                payload=payload,
            )
            event_id = event.id
            await session.commit()

        logger.info(
            "cloud_action_blocked",
            incident_id=str(incident_id),
            trace_id=trace_id,
            action=action,
        )
        return event_id
