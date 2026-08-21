"""The approval gate: the product's central rule."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.models.approval import ApprovalDecision
from app.models.incident import Incident
from app.models.maintenance import PartCheck
from app.models.work_order import WorkOrder
from app.services.approval import SIMULATED_WORK_ORDER_REFERENCE

pytestmark = pytest.mark.db

APPROVE_BODY = {
    "approver_id": "user-id",
    "approver_name": "A. Iyer",
    "reason": "Approved during scheduled changeover",
}
REJECT_BODY = {
    "approver_id": "user-id",
    "approver_name": "A. Iyer",
    "reason": "Window conflicts with production schedule",
}


async def test_approval_creates_decision_reservation_and_work_order(
    api: AsyncClient, main_incident: Incident
) -> None:
    response = await api.post(f"/incidents/{main_incident.id}/approve", json=APPROVE_BODY)

    assert response.status_code == 200
    body = response.json()

    assert body["decision"]["decision"] == "approved"
    assert body["decision"]["approver_name"] == "A. Iyer"
    assert body["decision"]["reason"] == APPROVE_BODY["reason"]

    # Token metadata is returned; the secret itself never is.
    assert body["token"]["token_id"]
    assert body["token"]["expires_at"]
    assert body["token"]["scope"].startswith(f"incident:{main_incident.id}:approve")
    assert "token" not in body["decision"]
    assert "token_hash" not in body["decision"]

    assert body["work_order_reference"] == SIMULATED_WORK_ORDER_REFERENCE == "WO-40219"
    # approval + approved transition + reservation + work order + live transition
    assert len(body["audit_event_ids"]) == 5

    incident = body["incident"]
    assert incident["workflow_status"] == "work_order_live"
    assert incident["work_order"]["external_reference"] == "WO-40219"
    assert incident["work_order"]["status"] == "open"
    part = incident["proposal"]["part_checks"][0]
    assert part["status"] == "reserved"
    assert part["reserved_at"] is not None
    assert incident["proposal"]["status"] == "approved"


async def test_approval_persists_only_a_token_hash(
    api: AsyncClient, main_incident: Incident, db_engine: AsyncEngine
) -> None:
    response = await api.post(f"/incidents/{main_incident.id}/approve", json=APPROVE_BODY)
    token_id = response.json()["token"]["token_id"]

    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    async with factory() as session:
        decision = (
            await session.execute(
                select(ApprovalDecision).where(ApprovalDecision.incident_id == main_incident.id)
            )
        ).scalar_one()

    assert str(decision.token_id) == token_id
    # A SHA-256 hex digest, not the raw secret.
    assert decision.token_hash is not None
    assert len(decision.token_hash) == 64
    assert decision.token_expires_at is not None
    assert decision.used_at is not None  # single use: spent on this operation


async def test_approval_is_refused_outside_approval_required(
    api: AsyncClient, main_incident: Incident
) -> None:
    """Approving twice must fail — the second call is no longer in the right state."""
    first = await api.post(f"/incidents/{main_incident.id}/approve", json=APPROVE_BODY)
    assert first.status_code == 200

    second = await api.post(f"/incidents/{main_incident.id}/approve", json=APPROVE_BODY)

    assert second.status_code == 409
    error = second.json()["error"]
    assert error["code"] == "APPROVAL_NOT_REQUIRED"
    assert error["details"]["current_state"] == "work_order_live"
    assert error["details"]["required_state"] == "approval_required"


async def test_approval_refused_for_incident_in_human_review(
    api: AsyncClient, low_confidence_incident: Incident
) -> None:
    response = await api.post(f"/incidents/{low_confidence_incident.id}/approve", json=APPROVE_BODY)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "APPROVAL_NOT_REQUIRED"


async def test_rejection_creates_no_reservation_and_no_work_order(
    api: AsyncClient, main_incident: Incident, db_engine: AsyncEngine
) -> None:
    response = await api.post(f"/incidents/{main_incident.id}/reject", json=REJECT_BODY)

    assert response.status_code == 200
    body = response.json()
    assert body["decision"]["decision"] == "rejected"
    assert body["decision"]["reason"] == REJECT_BODY["reason"]
    # rejection + rejected transition + return-to-watch transition
    assert len(body["audit_event_ids"]) == 3

    incident = body["incident"]
    assert incident["workflow_status"] == "watch"
    assert incident["work_order"] is None
    assert incident["proposal"]["part_checks"][0]["status"] == "checked_not_reserved"
    assert incident["proposal"]["part_checks"][0]["reserved_at"] is None

    # And nothing was written behind the API's back.
    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    async with factory() as session:
        work_orders = (
            (
                await session.execute(
                    select(WorkOrder).where(WorkOrder.incident_id == main_incident.id)
                )
            )
            .scalars()
            .all()
        )
        reserved = (
            (await session.execute(select(PartCheck).where(PartCheck.status == "reserved")))
            .scalars()
            .all()
        )
    assert work_orders == []
    assert reserved == []


async def test_rejection_records_both_transitions(
    api: AsyncClient, main_incident: Incident, audit_since
) -> None:
    """rejected -> watch must be an explicit audited transition, not a silent reset."""
    watermark = await audit_since.watermark(main_incident.id)

    await api.post(f"/incidents/{main_incident.id}/reject", json=REJECT_BODY)

    events = await audit_since(main_incident.id, watermark)
    transitions = [
        (
            event["event_payload_json"].get("previous_state"),
            event["event_payload_json"].get("next_state"),
        )
        for event in events
        if event["event_type"] == "workflow.transitioned"
    ]

    assert ("approval_required", "rejected") in transitions
    assert ("rejected", "watch") in transitions


async def test_rejection_refused_outside_approval_required(
    api: AsyncClient, offline_incident: Incident
) -> None:
    response = await api.post(f"/incidents/{offline_incident.id}/reject", json=REJECT_BODY)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "APPROVAL_NOT_REQUIRED"
