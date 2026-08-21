"""HTTP middleware: request-id propagation and structured access logging."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import bind_request_context, clear_request_context, get_logger
from app.core.request_context import (
    REQUEST_ID_HEADER,
    new_request_id,
    reset_request_id,
    set_request_id,
)

logger = get_logger("app.access")

RequestResponseEndpoint = Callable[[Request], Awaitable[Response]]


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request id, expose it on the response, and log the exchange.

    The incoming `X-Request-ID` header is reused when present so a trace can be
    followed across services; otherwise a fresh UUID4 is minted.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
        set_request_id(request_id)
        request.state.request_id = request_id
        bind_request_context(request_id=request_id)

        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            logger.info(
                "http_request",
                request_id=request_id,
                method=request.method,
                route=_route_template(request),
                path=request.url.path,
                status_code=status_code,
                duration_ms=duration_ms,
            )
            clear_request_context()
            reset_request_id()


def _route_template(request: Request) -> str:
    """The matched route pattern (e.g. `/api/v1/assets/{asset_id}`) when known."""
    route = request.scope.get("route")
    path_format = getattr(route, "path_format", None) or getattr(route, "path", None)
    return path_format or request.url.path
