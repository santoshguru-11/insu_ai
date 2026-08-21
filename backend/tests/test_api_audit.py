"""The audit trail covers every workflow transition."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.incident import Incident

pytestmark = pytest.mark.db

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


async def test_audit_timeline_is_chronological_and_paginated(
    api: AsyncClient, main_incident: Incident
) -> None:
    await api.post(f"/incidents/{main_incident.id}/approve", json=APPROVE_BODY)

    response = await api.get(f"/incidents/{main_incident.id}/audit")

    assert response.status_code == 200
    body = response.json()
    timestamps = [event["occurred_at"] for event in body["items"]]
    assert timestamps == sorted(timestamps)
    assert body["total"] == len(body["items"])

    page = await api.get(f"/incidents/{main_incident.id}/audit", params={"limit": 2, "offset": 0})
    assert len(page.json()["items"]) == 2
    assert page.json()["total"] == body["total"]
    assert page.json()["items"] == body["items"][:2]


async def test_every_transition_produces_an_audit_event(
    api: AsyncClient, main_incident: Incident, audit_since
) -> None:
    """Walk the full happy path and check the trail records each state change."""
    watermark = await audit_since.watermark(main_incident.id)

    await api.post(f"/incidents/{main_incident.id}/approve", json=APPROVE_BODY)
    await api.post(f"/incidents/{main_incident.id}/outcome", json=OUTCOME_BODY)

    events = await audit_since(main_incident.id, watermark)

    transitions = [
        (
            event["event_payload_json"]["previous_state"],
            event["event_payload_json"]["next_state"],
        )
        for event in events
        if event["event_type"] == "workflow.transitioned"
    ]
    assert transitions == [
        ("approval_required", "approved"),
        ("approved", "work_order_live"),
        ("work_order_live", "resolved"),
    ]

    # Every transition event carries the full context the audit rule requires.
    for event in events:
        if event["event_type"] != "workflow.transitioned":
            continue
        payload = event["event_payload_json"]
        assert payload["previous_state"]
        assert payload["next_state"]
        assert "reason" in payload
        assert event["trace_id"] == "tr_9f21"
        assert event["incident_id"] == str(main_incident.id)
        assert event["actor_type"] in {"human", "agent", "system", "external_system"}
        assert event["occurred_at"]


async def test_approval_precedes_the_actions_it_authorises(
    api: AsyncClient, main_incident: Incident, audit_since
) -> None:
    """The trail must prove no irreversible step ran before the approval."""
    watermark = await audit_since.watermark(main_incident.id)

    await api.post(f"/incidents/{main_incident.id}/approve", json=APPROVE_BODY)

    events = await audit_since(main_incident.id, watermark)
    order = [event["event_type"] for event in events]

    approval_at = order.index("approval.created")
    reservation_at = order.index("part.reserved")
    work_order_at = order.index("work_order.created")

    assert approval_at < reservation_at < work_order_at


async def test_audit_events_are_written_for_each_distinct_action(
    api: AsyncClient, main_incident: Incident, audit_since
) -> None:
    watermark = await audit_since.watermark(main_incident.id)

    await api.post(f"/incidents/{main_incident.id}/approve", json=APPROVE_BODY)
    await api.post(f"/incidents/{main_incident.id}/outcome", json=OUTCOME_BODY)

    events = await audit_since(main_incident.id, watermark)
    types = {event["event_type"] for event in events}

    assert {
        "approval.created",
        "part.reserved",
        "work_order.created",
        "outcome.captured",
        "workflow.transitioned",
    } <= types


async def test_rejected_path_records_no_reservation_or_work_order_events(
    api: AsyncClient, main_incident: Incident, audit_since
) -> None:
    watermark = await audit_since.watermark(main_incident.id)

    await api.post(
        f"/incidents/{main_incident.id}/reject",
        json={"approver_id": "u", "approver_name": "A. Iyer", "reason": "Window conflict"},
    )

    events = await audit_since(main_incident.id, watermark)
    types = {event["event_type"] for event in events}

    assert "approval.rejected" in types
    assert "part.reserved" not in types
    assert "work_order.created" not in types
