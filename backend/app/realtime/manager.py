"""In-memory WebSocket connection manager.

Scope note: this holds subscribers in a process-local dict, so a broadcast only
reaches clients attached to *this* backend instance. That is fine for the demo,
which runs a single process. Running more than one instance (or any autoscaled
deployment) requires moving the fan-out behind a shared bus — Redis pub/sub, NATS,
or Postgres LISTEN/NOTIFY — with each instance subscribing to the channel and
relaying to its own local sockets. The publish/subscribe surface below is kept
deliberately narrow so that swap touches only this file.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from typing import Any

from starlette.websockets import WebSocket, WebSocketState

from app.core.logging import get_logger
from app.schemas.websocket import WebSocketEvent, WebSocketEventType

logger = get_logger(__name__)


class ConnectionManager:
    """Tracks who is watching which incident, and pushes events to them."""

    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, incident_id: uuid.UUID, websocket: WebSocket) -> None:
        """Accept the socket and subscribe it to one incident's channel."""
        await websocket.accept()
        async with self._lock:
            self._connections[incident_id].add(websocket)
        logger.info(
            "websocket_connected",
            incident_id=str(incident_id),
            subscribers=len(self._connections[incident_id]),
        )

    async def disconnect(self, incident_id: uuid.UUID, websocket: WebSocket) -> None:
        """Drop a socket, and the channel too once its last subscriber leaves."""
        async with self._lock:
            subscribers = self._connections.get(incident_id)
            if subscribers is None:
                return
            subscribers.discard(websocket)
            if not subscribers:
                del self._connections[incident_id]
        logger.info("websocket_disconnected", incident_id=str(incident_id))

    async def broadcast(self, event: WebSocketEvent) -> int:
        """Send `event` to every live subscriber; returns how many got it.

        Sockets that fail to receive are dropped rather than retried — a broken
        console must not stall a workflow transition.
        """
        async with self._lock:
            subscribers = list(self._connections.get(event.incident_id, ()))

        if not subscribers:
            return 0

        message = event.model_dump(mode="json")
        delivered = 0
        stale: list[WebSocket] = []
        for websocket in subscribers:
            if websocket.client_state is not WebSocketState.CONNECTED:
                stale.append(websocket)
                continue
            try:
                await websocket.send_json(message)
                delivered += 1
            except Exception:  # a disconnect can surface as almost anything
                stale.append(websocket)

        for websocket in stale:
            await self.disconnect(event.incident_id, websocket)

        logger.info(
            "websocket_broadcast",
            event_type=str(event.event_type),
            incident_id=str(event.incident_id),
            delivered=delivered,
            dropped=len(stale),
        )
        return delivered

    async def publish(
        self,
        *,
        event_type: WebSocketEventType,
        incident_id: uuid.UUID,
        trace_id: str,
        data: dict[str, Any] | None = None,
    ) -> int:
        """Convenience wrapper that builds the envelope and broadcasts it."""
        return await self.broadcast(
            WebSocketEvent(
                event_type=event_type,
                incident_id=incident_id,
                trace_id=trace_id,
                data=data or {},
            )
        )

    def subscriber_count(self, incident_id: uuid.UUID) -> int:
        return len(self._connections.get(incident_id, ()))


#: Process-wide singleton. See the module docstring before scaling out.
connection_manager = ConnectionManager()
