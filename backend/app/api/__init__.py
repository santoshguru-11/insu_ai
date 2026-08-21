"""HTTP routing."""

from app.api.v1 import api_router
from app.api.v1.websocket import router as websocket_router

__all__ = ["api_router", "websocket_router"]
