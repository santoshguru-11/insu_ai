"""Incident endpoints: list, detail, audit timeline, and the workflow actions."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import (
    ApprovalServiceDep,
    ConnectionManagerDep,
    IncidentDep,
    IncidentIdPath,
    IncidentViewDep,
    OutcomeServiceDep,
    SessionDep,
    SimulationServiceDep,
)
from app.models.enums import ScenarioType, Severity, WorkflowStatus
from app.repositories.audit_event import AuditEventRepository
from app.repositories.incident import IncidentRepository
from app.schemas.approval import ApprovalRequest
from app.schemas.audit import AuditEventRead
from app.schemas.common import ErrorResponse, Page
from app.schemas.incident import (
    ApprovalResponse,
    AuditTimeline,
    IncidentDetail,
    IncidentListItem,
    OutcomeResponse,
    RejectionResponse,
    SimulateNextStepRequest,
    SimulateNextStepResponse,
)
from app.schemas.maintenance import TechnicianOutcomeCreate, TechnicianOutcomeRead, WorkOrderRead
from app.schemas.websocket import WebSocketEventType
from app.services.incident_view import build_list_item

router = APIRouter(prefix="/incidents", tags=["incidents"])

_CONFLICT_RESPONSES = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Unknown incident."},
    status.HTTP_409_CONFLICT: {
        "model": ErrorResponse,
        "description": "The incident is not in a state that allows this action.",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ErrorResponse,
        "description": "Cloud services are unreachable for this asset (CLOUD_UNAVAILABLE).",
    },
}


@router.get(
    "",
    response_model=Page[IncidentListItem],
    summary="List incidents",
    description=(
        "Paginated incident list, newest detection first. Each row carries the "
        "asset name, trace id, a diagnosis summary and the RUL estimate so the "
        "console can render the board without a second request per incident."
    ),
)
async def list_incidents(
    session: SessionDep,
    workflow_status: Annotated[
        WorkflowStatus | None, Query(description="Only incidents in this workflow state.")
    ] = None,
    severity: Annotated[
        Severity | None, Query(description="Only incidents at this ISO 20816-3 band.")
    ] = None,
    asset_id: Annotated[
        uuid.UUID | None, Query(description="Only incidents on this asset.")
    ] = None,
    scenario_type: Annotated[
        ScenarioType | None, Query(description="Only incidents from this demo scenario.")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[IncidentListItem]:
    repository = IncidentRepository(session)
    filters = {
        "workflow_status": workflow_status,
        "severity": severity,
        "asset_id": asset_id,
        "scenario_type": scenario_type,
    }
    rows = await repository.list_filtered(**filters, limit=limit, offset=offset)
    total = await repository.count_filtered(**filters)
    return Page[IncidentListItem](
        items=[build_list_item(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{incident_id}",
    response_model=IncidentDetail,
    summary="Get full incident detail",
    description=(
        "Everything the console renders for one incident: asset, sentinel "
        "anomalies, agent runs, diagnosis with evidence and rejected "
        "alternatives, RUL, maintenance proposal, part checks, approval state, "
        "work order, technician outcome, cloud availability and workflow state."
    ),
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
)
async def get_incident(incident_id: IncidentIdPath, view: IncidentViewDep) -> IncidentDetail:
    return await view.detail(incident_id)


@router.get(
    "/{incident_id}/audit",
    response_model=AuditTimeline,
    summary="Get the incident audit timeline",
    description=(
        "Append-only audit events for this incident, oldest first. Every "
        "workflow transition, approval, reservation, work-order creation and "
        "blocked cloud action appears here."
    ),
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
)
async def get_incident_audit(
    incident: IncidentDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditTimeline:
    repository = AuditEventRepository(session)
    events = await repository.list_by_incident(incident.id, limit=limit, offset=offset)
    return AuditTimeline(
        items=[AuditEventRead.model_validate(event) for event in events],
        total=await repository.count_by_incident(incident.id),
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{incident_id}/approve",
    response_model=ApprovalResponse,
    summary="Approve the maintenance proposal",
    description=(
        "Records a human approval, then performs the work it authorises: a "
        "simulated part reservation and a simulated work order. Requires the "
        "incident to be in `approval_required`, and is refused when the asset's "
        "cloud link is down. Approval, reservation and work-order creation are "
        "audited separately, in that order."
    ),
    responses=_CONFLICT_RESPONSES,
)
async def approve_incident(
    incident: IncidentDep,
    payload: ApprovalRequest,
    service: ApprovalServiceDep,
    view: IncidentViewDep,
    manager: ConnectionManagerDep,
) -> ApprovalResponse:
    outcome = await service.approve(incident, payload)
    detail = await view.detail(incident.id)

    await manager.publish(
        event_type=WebSocketEventType.APPROVAL_CREATED,
        incident_id=incident.id,
        trace_id=incident.trace_id,
        data={
            "approval_decision_id": str(outcome.decision.id),
            "approver_name": payload.approver_name,
            "token_id": str(outcome.token.token_id),
        },
    )
    if outcome.reserved_part_check_ids:
        await manager.publish(
            event_type=WebSocketEventType.PART_RESERVED,
            incident_id=incident.id,
            trace_id=incident.trace_id,
            data={"part_check_ids": [str(pk) for pk in outcome.reserved_part_check_ids]},
        )
    await manager.publish(
        event_type=WebSocketEventType.WORK_ORDER_CREATED,
        incident_id=incident.id,
        trace_id=incident.trace_id,
        data={"work_order_reference": outcome.work_order_reference},
    )
    await manager.publish(
        event_type=WebSocketEventType.INCIDENT_UPDATED,
        incident_id=incident.id,
        trace_id=incident.trace_id,
        data={"workflow_status": str(detail.workflow_status)},
    )

    return ApprovalResponse(
        decision=outcome.decision,
        token=outcome.token,
        work_order_reference=outcome.work_order_reference,
        audit_event_ids=outcome.audit_event_ids,
        incident=detail,
    )


@router.post(
    "/{incident_id}/reject",
    response_model=RejectionResponse,
    summary="Reject the maintenance proposal",
    description=(
        "Records a rejection and returns the asset to `watch` as an explicit, "
        "audited transition. Reserves no stock and creates no work order."
    ),
    responses=_CONFLICT_RESPONSES,
)
async def reject_incident(
    incident: IncidentDep,
    payload: ApprovalRequest,
    service: ApprovalServiceDep,
    view: IncidentViewDep,
    manager: ConnectionManagerDep,
) -> RejectionResponse:
    outcome = await service.reject(incident, payload)
    detail = await view.detail(incident.id)

    await manager.publish(
        event_type=WebSocketEventType.APPROVAL_REJECTED,
        incident_id=incident.id,
        trace_id=incident.trace_id,
        data={
            "approval_decision_id": str(outcome.decision.id),
            "approver_name": payload.approver_name,
            "reason": payload.reason,
        },
    )
    await manager.publish(
        event_type=WebSocketEventType.INCIDENT_UPDATED,
        incident_id=incident.id,
        trace_id=incident.trace_id,
        data={"workflow_status": str(detail.workflow_status)},
    )
    return RejectionResponse(
        decision=outcome.decision,
        audit_event_ids=outcome.audit_event_ids,
        incident=detail,
    )


@router.post(
    "/{incident_id}/simulate-next-step",
    response_model=SimulateNextStepResponse,
    summary="Advance the guided demo one step",
    description=(
        "Takes the next legal transition for this incident using the seeded "
        "simulated data. It never crosses the approval gate: an incident in "
        "`approval_required` or `human_review` is returned unchanged with "
        "`advanced: false` and an explanation."
    ),
    responses=_CONFLICT_RESPONSES,
)
async def simulate_next_step(
    incident: IncidentDep,
    payload: SimulateNextStepRequest,
    service: SimulationServiceDep,
    view: IncidentViewDep,
    manager: ConnectionManagerDep,
) -> SimulateNextStepResponse:
    step = await service.next_step(
        incident,
        actor_id=payload.actor_id,
        actor_type=payload.actor_type,
        reason=payload.reason,
    )
    detail = await view.detail(incident.id)

    if step.advanced:
        await manager.publish(
            event_type=WebSocketEventType.INCIDENT_UPDATED,
            incident_id=incident.id,
            trace_id=incident.trace_id,
            data={
                "previous_state": str(step.previous_state),
                "workflow_status": str(step.next_state),
                "detail": step.detail,
            },
        )

    return SimulateNextStepResponse(
        previous_state=step.previous_state,
        workflow_status=step.next_state,
        advanced=step.advanced,
        detail=step.detail,
        changed_records=step.changed_records,
        audit_event_ids=step.audit_event_ids,
        incident=detail,
    )


@router.post(
    "/{incident_id}/outcome",
    response_model=OutcomeResponse,
    summary="Capture the technician outcome",
    description=(
        "Records what the technician actually found, completes the work order "
        "and resolves the incident. Requires `work_order_live`."
    ),
    responses=_CONFLICT_RESPONSES,
)
async def capture_outcome(
    incident: IncidentDep,
    payload: TechnicianOutcomeCreate,
    service: OutcomeServiceDep,
    view: IncidentViewDep,
    manager: ConnectionManagerDep,
) -> OutcomeResponse:
    result = await service.capture(incident, payload)
    detail = await view.detail(incident.id)

    await manager.publish(
        event_type=WebSocketEventType.OUTCOME_CAPTURED,
        incident_id=incident.id,
        trace_id=incident.trace_id,
        data={
            "technician_outcome_id": str(result.outcome.id),
            "diagnosis_confirmed": payload.diagnosis_confirmed,
            "technician_name": payload.technician_name,
        },
    )
    await manager.publish(
        event_type=WebSocketEventType.INCIDENT_UPDATED,
        incident_id=incident.id,
        trace_id=incident.trace_id,
        data={"workflow_status": str(detail.workflow_status)},
    )
    return OutcomeResponse(
        outcome=TechnicianOutcomeRead.model_validate(result.outcome),
        work_order=WorkOrderRead.model_validate(result.work_order),
        audit_event_ids=result.audit_event_ids,
        incident=detail,
    )
