"""Per-request identity, stored in a context variable."""

from __future__ import annotations

import uuid
from contextvars import ContextVar

REQUEST_ID_HEADER = "X-Request-ID"

_request_id: ContextVar[str] = ContextVar("request_id", default="")


def new_request_id() -> str:
    return str(uuid.uuid4())


def set_request_id(request_id: str) -> None:
    _request_id.set(request_id)


def get_request_id() -> str:
    """Current request id, generating one when called outside a request."""
    request_id = _request_id.get()
    if not request_id:
        request_id = new_request_id()
        _request_id.set(request_id)
    return request_id


def reset_request_id() -> None:
    _request_id.set("")
