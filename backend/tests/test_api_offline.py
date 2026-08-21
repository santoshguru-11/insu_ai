"""Scenario C: the WAN link is down.

Edge artefacts stay readable; every cloud-dependent action is refused with
`CLOUD_UNAVAILABLE` and the refusal is recorded in the audit trail.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.incident import Incident

pytestmark = pytest.mark.db

STEP_BODY = {"actor_id": "demo-user", "actor_type": "system"}
APPROVE_BODY = {"approver_id": "user-id", "approver_name": "A. Iyer", "reason": "Go ahead"}


async def test_edge_diagnosis_remains_readable(
    api: AsyncClient, offline_incident: Incident
) -> None:
    response = await api.get(f"/incidents/{offline_incident.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["cloud_available"] is False
    assert body["workflow_status"] == "diagnosed"
    # The whole point: the diagnosis survived the outage.
    assert body["diagnosis"]["failure_mode_code"] == "ROTOR_IMBALANCE"
    assert body["diagnosis"]["confidence"] == pytest.approx(0.81)
    assert len(body["diagnosis"]["evidence_items"]) == 2
    assert body["rul"]["estimate_days"] == pytest.approx(24.0)
    assert body["anomalies"][0]["signal_name"] == "fan_1x_radial_velocity"


@pytest.mark.parametrize("action", ["simulate-next-step", "approve"])
async def test_cloud_actions_are_refused(
    api: AsyncClient, offline_incident: Incident, action: str
) -> None:
    payload = STEP_BODY if action == "simulate-next-step" else APPROVE_BODY

    response = await api.post(f"/incidents/{offline_incident.id}/{action}", json=payload)

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "CLOUD_UNAVAILABLE"
    assert error["details"]["edge_diagnosis_available"] is True
    assert error["details"]["trace_id"] == "tr_1d88"


async def test_blocked_action_is_audited_and_survives_the_failed_request(
    api: AsyncClient, offline_incident: Incident, audit_since
) -> None:
    """The refusal rolls the request back — the audit record must outlive it."""
    watermark = await audit_since.watermark(offline_incident.id)

    await api.post(f"/incidents/{offline_incident.id}/simulate-next-step", json=STEP_BODY)
    await api.post(f"/incidents/{offline_incident.id}/approve", json=APPROVE_BODY)

    events = await audit_since(offline_incident.id, watermark)
    blocked = [event for event in events if event["event_type"] == "cloud.action_blocked"]

    assert len(blocked) == 2
    actions = {event["event_payload_json"]["action"] for event in blocked}
    assert "approve" in actions
    assert any(action.startswith("simulate_next_step") for action in actions)
    for event in blocked:
        assert event["event_payload_json"]["edge_diagnosis_preserved"] is True
        assert event["event_payload_json"]["reason"] == "cloud_unavailable"


async def test_blocked_actions_change_nothing(api: AsyncClient, offline_incident: Incident) -> None:
    before = (await api.get(f"/incidents/{offline_incident.id}")).json()

    await api.post(f"/incidents/{offline_incident.id}/approve", json=APPROVE_BODY)

    after = (await api.get(f"/incidents/{offline_incident.id}")).json()
    assert after["workflow_status"] == before["workflow_status"] == "diagnosed"
    assert after["approval"] is None
    assert after["work_order"] is None
    assert after["proposal"] is None
