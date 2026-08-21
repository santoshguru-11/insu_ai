"""Realtime incident channel.

A console opens one socket per incident it is watching. The server sends a
snapshot immediately, then pushes an event after every workflow transition,
approval, rejection, reservation, work-order creation and technician outcome.

Fan-out is process-local; see `app.realtime.manager` for what changes when this
runs on more than one instance.
"""

from __future__ import annotations

import contextlib
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.deps import get_connection_manager
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.db.session import get_session_factory
from app.schemas.websocket import WebSocketEvent, WebSocketEventType
from app.services.incident_view import IncidentViewService

logger = get_logger(__name__)

router = APIRouter(tags=["realtime"])

#: Closure codes. 4004 mirrors "not found" for a channel that cannot exist.
WS_INCIDENT_NOT_FOUND = 4004
WS_INTERNAL_ERROR = 1011


@router.websocket("/ws/incidents/{incident_id}")
async def incident_channel(websocket: WebSocket, incident_id: uuid.UUID) -> None:
    """Stream updates for one incident.

    The socket is read-only from the client's side: anything it sends is drained
    and ignored, which doubles as the disconnect detector.
    """
    manager = get_connection_manager()

    # Load the snapshot on its own session before accepting, so an unknown
    # incident is refused rather than left hanging on an open socket.
    try:
        async with get_session_factory()() as session:
            snapshot = await IncidentViewService(session).detail(incident_id)
    except AppError:
        await websocket.close(code=WS_INCIDENT_NOT_FOUND, reason="Unknown incident")
        return

    await manager.connect(incident_id, websocket)
    try:
        await websocket.send_json(
            WebSocketEvent(
                event_type=WebSocketEventType.SNAPSHOT,
                incident_id=incident_id,
                trace_id=snapshot.trace_id,
                data={"incident": snapshot.model_dump(mode="json")},
            ).model_dump(mode="json")
        )

        while True:
            # Client messages carry no meaning yet; receiving keeps the socket
            # alive and raises WebSocketDisconnect the moment it drops.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("websocket_channel_error", incident_id=str(incident_id))
        with contextlib.suppress(RuntimeError):  # already closed
            await websocket.close(code=WS_INTERNAL_ERROR)
    finally:
        await manager.disconnect(incident_id, websocket)
