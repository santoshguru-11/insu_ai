"""Simulation stepping, invalid transitions, and outcome capture."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.exceptions import InvalidTransitionError
from app.models.enums import ActorType, WorkflowStatus
from app.models.incident import Incident
from app.services.workflow import ALLOWED_TRANSITIONS, WorkflowService, can_transition

pytestmark = pytest.mark.db

STEP_BODY = {"actor_id": "demo-user", "actor_type": "system", "reason": "Advance guided demo"}
APPROVE_BODY = {
    "approver_id": "user-id",
    "approver_name": "A. Iyer",
    "reason": "Approved during scheduled changeover",
}
OUTCOME_BODY = {
    "technician_id": "tech-001",
    "technician_name": "R. Kumar",
    "diagnosis_confirmed": True,
    "actual_finding": "Outer-race bearing wear with visible spalling",
    "parts_used": ["BRG-6220-C3"],
    "technician_note": "Bearing replaced during planned changeover.",
    "repair_duration_hours": 4.5,
}


def test_state_machine_matches_the_specification() -> None:
    """The allowed edges are exactly the ten the product defines."""
    edges = {
        (source, target) for source, targets in ALLOWED_TRANSITIONS.items() for target in targets
    }
    assert edges == {
        (WorkflowStatus.WATCH, WorkflowStatus.ESCALATED),
        (WorkflowStatus.ESCALATED, WorkflowStatus.DIAGNOSED),
        (WorkflowStatus.DIAGNOSED, WorkflowStatus.HUMAN_REVIEW),
        (WorkflowStatus.DIAGNOSED, WorkflowStatus.APPROVAL_REQUIRED),
        (WorkflowStatus.HUMAN_REVIEW, WorkflowStatus.APPROVAL_REQUIRED),
        (WorkflowStatus.APPROVAL_REQUIRED, WorkflowStatus.APPROVED),
        (WorkflowStatus.APPROVAL_REQUIRED, WorkflowStatus.REJECTED),
        (WorkflowStatus.APPROVED, WorkflowStatus.WORK_ORDER_LIVE),
        (WorkflowStatus.WORK_ORDER_LIVE, WorkflowStatus.RESOLVED),
        (WorkflowStatus.REJECTED, WorkflowStatus.WATCH),
    }
    # Nothing may skip the approval gate.
    assert not can_transition(WorkflowStatus.DIAGNOSED, WorkflowStatus.APPROVED)
    assert not can_transition(WorkflowStatus.DIAGNOSED, WorkflowStatus.WORK_ORDER_LIVE)
    assert not can_transition(WorkflowStatus.WATCH, WorkflowStatus.WORK_ORDER_LIVE)


async def test_invalid_transition_is_rejected_with_useful_detail(
    main_incident: Incident, db_engine
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    async with factory() as session:
        incident = await session.get(Incident, main_incident.id)
        assert incident is not None
        service = WorkflowService(session)

        with pytest.raises(InvalidTransitionError) as excinfo:
            await service.transition(incident, WorkflowStatus.RESOLVED, actor_type=ActorType.SYSTEM)

    error = excinfo.value
    assert error.code == "INVALID_WORKFLOW_TRANSITION"
    assert error.status_code == 409
    assert error.details["current_state"] == "approval_required"
    assert error.details["requested_state"] == "resolved"
    assert sorted(error.details["allowed_next_states"]) == ["approved", "rejected"]


async def test_transition_is_idempotent(main_incident: Incident, db_engine) -> None:
    """Re-requesting the current state changes nothing and audits nothing."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    async with factory() as session:
        incident = await session.get(Incident, main_incident.id)
        assert incident is not None
        result = await WorkflowService(session).transition(
            incident, WorkflowStatus.APPROVAL_REQUIRED, actor_type=ActorType.SYSTEM
        )

    assert result.changed is False
    assert result.audit_event_ids == []
    assert result.previous_state == result.next_state == WorkflowStatus.APPROVAL_REQUIRED


async def test_simulation_will_not_cross_the_approval_gate(
    api: AsyncClient, main_incident: Incident
) -> None:
    response = await api.post(f"/incidents/{main_incident.id}/simulate-next-step", json=STEP_BODY)

    assert response.status_code == 200
    body = response.json()
    assert body["advanced"] is False
    assert body["workflow_status"] == "approval_required"
    assert body["previous_state"] == "approval_required"
    assert "approve" in body["detail"]
    assert body["audit_event_ids"] == []


async def test_low_confidence_incident_cannot_auto_advance(
    api: AsyncClient, low_confidence_incident: Incident
) -> None:
    """Scenario B stays in human_review however many times it is stepped."""
    for _ in range(3):
        response = await api.post(
            f"/incidents/{low_confidence_incident.id}/simulate-next-step", json=STEP_BODY
        )
        assert response.status_code == 200
        body = response.json()
        assert body["advanced"] is False
        assert body["workflow_status"] == "human_review"

    detail = await api.get(f"/incidents/{low_confidence_incident.id}")
    incident = detail.json()
    assert incident["workflow_status"] == "human_review"
    assert incident["diagnosis"]["confidence"] < 0.60
    assert incident["diagnosis"]["confidence_band"] == "low"
    # Two plausible failure modes, and nothing planned or reserved.
    assert len(incident["diagnosis"]["alternatives"]) == 2
    assert incident["human_review_reason"]
    assert incident["proposal"] is None
    assert incident["work_order"] is None


async def test_rejected_incident_walks_forward_again_from_watch(
    api: AsyncClient, main_incident: Incident
) -> None:
    """After a rejection the sentinel can re-escalate: watch -> escalated -> diagnosed."""
    await api.post(
        f"/incidents/{main_incident.id}/reject",
        json={"approver_id": "u", "approver_name": "A. Iyer", "reason": "Window conflict"},
    )

    first = await api.post(f"/incidents/{main_incident.id}/simulate-next-step", json=STEP_BODY)
    assert first.json()["workflow_status"] == "escalated"
    assert first.json()["advanced"] is True

    second = await api.post(f"/incidents/{main_incident.id}/simulate-next-step", json=STEP_BODY)
    assert second.json()["workflow_status"] == "diagnosed"

    third = await api.post(f"/incidents/{main_incident.id}/simulate-next-step", json=STEP_BODY)
    assert third.json()["workflow_status"] == "approval_required"


async def test_outcome_capture_resolves_the_incident(
    api: AsyncClient, main_incident: Incident
) -> None:
    await api.post(f"/incidents/{main_incident.id}/approve", json=APPROVE_BODY)

    response = await api.post(f"/incidents/{main_incident.id}/outcome", json=OUTCOME_BODY)

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"]["technician_name"] == "R. Kumar"
    assert body["outcome"]["diagnosis_confirmed"] is True
    assert body["outcome"]["parts_used_json"] == ["BRG-6220-C3"]
    assert body["outcome"]["repair_duration_hours"] == pytest.approx(4.5)
    assert body["work_order"]["status"] == "completed"
    assert body["work_order"]["completed_at"] is not None
    assert body["incident"]["workflow_status"] == "resolved"
    assert body["incident"]["resolved_at"] is not None


async def test_outcome_refused_before_the_work_order_is_live(
    api: AsyncClient, main_incident: Incident
) -> None:
    response = await api.post(f"/incidents/{main_incident.id}/outcome", json=OUTCOME_BODY)

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "WORK_ORDER_NOT_LIVE"
    assert error["details"]["current_state"] == "approval_required"


async def test_resolved_incident_is_terminal(api: AsyncClient, main_incident: Incident) -> None:
    await api.post(f"/incidents/{main_incident.id}/approve", json=APPROVE_BODY)
    await api.post(f"/incidents/{main_incident.id}/outcome", json=OUTCOME_BODY)

    step = await api.post(f"/incidents/{main_incident.id}/simulate-next-step", json=STEP_BODY)

    assert step.json()["advanced"] is False
    assert step.json()["workflow_status"] == "resolved"
    assert not ALLOWED_TRANSITIONS[WorkflowStatus.RESOLVED]
