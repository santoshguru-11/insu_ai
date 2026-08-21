"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.audit import AuditService

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_request_id_dep(request: Request) -> str:
    """The id assigned to this request by `RequestContextMiddleware`."""
    return getattr(request.state, "request_id", "")


RequestIdDep = Annotated[str, Depends(get_request_id_dep)]


def get_audit_service(session: SessionDep) -> AuditService:
    return AuditService(session)


AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
