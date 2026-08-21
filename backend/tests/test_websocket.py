"""The realtime incident channel."""

from __future__ import annotations

import uuid

import pytest
from starlette.testclient import TestClient

from app.main import app
from app.models.incident import Incident
from app.realtime.manager import ConnectionManager, connection_manager
from app.schemas.websocket import WebSocketEventType

pytestmark = pytest.mark.db

APPROVE_BODY = {
    "approver_id": "user-id",
    "approver_name": "A. Iyer",
    "reason": "Approved during scheduled changeover",
}


def _receive(websocket, count: int) -> list[dict]:
    """Read exactly `count` frames.

    `TestClient` sockets have no receive timeout, so the tests assert on a known
    number of frames rather than draining until empty — which would block
    forever on the frame after the last one.
    """
    return [websocket.receive_json() for _ in range(count)]


async def test_snapshot_is_sent_on_connect(
    main_incident: Incident, in_test_client, api_prefix: str
) -> None:
    """A newly connected console gets the current incident immediately."""
    incident_id = main_incident.id

    def _run() -> dict:
        with (
            TestClient(app) as client,
            client.websocket_connect(f"/ws/incidents/{incident_id}") as websocket,
        ):
            return websocket.receive_json()

    snapshot = await in_test_client(_run)

    assert snapshot["event_type"] == WebSocketEventType.SNAPSHOT
    assert snapshot["incident_id"] == str(incident_id)
    assert snapshot["trace_id"] == "tr_9f21"
    assert snapshot["occurred_at"]
    incident = snapshot["data"]["incident"]
    assert incident["workflow_status"] == "approval_required"
    assert incident["diagnosis"]["failure_mode_code"] == "BRG_OUTER_RACE_WEAR"


async def test_approval_broadcasts_workflow_update(
    main_incident: Incident, in_test_client, api_prefix: str
) -> None:
    """Approving must push approval, reservation, work-order and update events."""
    incident_id = main_incident.id

    def _run() -> list[dict]:
        with (
            TestClient(app) as client,
            client.websocket_connect(f"/ws/incidents/{incident_id}") as websocket,
        ):
            snapshot = websocket.receive_json()
            assert snapshot["event_type"] == WebSocketEventType.SNAPSHOT

            response = client.post(
                f"{api_prefix}/incidents/{incident_id}/approve", json=APPROVE_BODY
            )
            assert response.status_code == 200
            # approval.created, part.reserved, work_order.created, incident.updated
            return _receive(websocket, 4)

    events = await in_test_client(_run)
    by_type = {event["event_type"]: event for event in events}

    assert WebSocketEventType.APPROVAL_CREATED in by_type
    assert WebSocketEventType.PART_RESERVED in by_type
    assert WebSocketEventType.WORK_ORDER_CREATED in by_type
    assert WebSocketEventType.INCIDENT_UPDATED in by_type

    update = by_type[WebSocketEventType.INCIDENT_UPDATED]
    assert update["incident_id"] == str(incident_id)
    assert update["trace_id"] == "tr_9f21"
    assert update["occurred_at"]
    assert update["data"]["workflow_status"] == "work_order_live"

    assert (
        by_type[WebSocketEventType.WORK_ORDER_CREATED]["data"]["work_order_reference"] == "WO-40219"
    )
    assert by_type[WebSocketEventType.APPROVAL_CREATED]["data"]["approver_name"] == "A. Iyer"


async def test_rejection_broadcasts_rejection_event(
    main_incident: Incident, in_test_client, api_prefix: str
) -> None:
    incident_id = main_incident.id

    def _run() -> list[dict]:
        with (
            TestClient(app) as client,
            client.websocket_connect(f"/ws/incidents/{incident_id}") as websocket,
        ):
            websocket.receive_json()  # snapshot
            response = client.post(
                f"{api_prefix}/incidents/{incident_id}/reject",
                json={"approver_id": "u", "approver_name": "A. Iyer", "reason": "Conflict"},
            )
            assert response.status_code == 200
            # approval.rejected, incident.updated — and nothing else.
            return _receive(websocket, 2)

    events = await in_test_client(_run)
    by_type = {event["event_type"]: event for event in events}

    assert WebSocketEventType.APPROVAL_REJECTED in by_type
    assert by_type[WebSocketEventType.INCIDENT_UPDATED]["data"]["workflow_status"] == "watch"
    # A rejection reserves nothing and creates no work order — so no such events.
    assert WebSocketEventType.PART_RESERVED not in by_type
    assert WebSocketEventType.WORK_ORDER_CREATED not in by_type


async def test_unknown_incident_is_refused(in_test_client) -> None:
    unknown = uuid.uuid4()

    def _run() -> bool:
        with TestClient(app) as client:
            try:
                with client.websocket_connect(f"/ws/incidents/{unknown}"):
                    return False
            except Exception:
                return True

    assert await in_test_client(_run) is True


async def test_manager_drops_disconnected_clients(main_incident: Incident, in_test_client) -> None:
    """Sockets must be unregistered on disconnect, not leaked."""
    incident_id = main_incident.id

    def _run() -> None:
        with (
            TestClient(app) as client,
            client.websocket_connect(f"/ws/incidents/{incident_id}") as websocket,
        ):
            websocket.receive_json()

    await in_test_client(_run)

    assert connection_manager.subscriber_count(incident_id) == 0


async def test_broadcast_to_nobody_is_a_no_op() -> None:
    manager = ConnectionManager()

    delivered = await manager.publish(
        event_type=WebSocketEventType.INCIDENT_UPDATED,
        incident_id=uuid.uuid4(),
        trace_id="tr_none",
        data={},
    )

    assert delivered == 0
