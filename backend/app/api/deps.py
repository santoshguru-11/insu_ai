"""Shared FastAPI dependencies."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.incident import Incident
from app.realtime.manager import ConnectionManager, connection_manager
from app.services.approval import ApprovalService
from app.services.audit import AuditService
from app.services.incident_view import IncidentViewService
from app.services.outcome import OutcomeService
from app.services.simulation import SimulationService
from app.services.workflow import WorkflowService

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_request_id_dep(request: Request) -> str:
    """The id assigned to this request by `RequestContextMiddleware`."""
    return getattr(request.state, "request_id", "")


RequestIdDep = Annotated[str, Depends(get_request_id_dep)]


def get_audit_service(session: SessionDep) -> AuditService:
    return AuditService(session)


def get_workflow_service(session: SessionDep) -> WorkflowService:
    return WorkflowService(session)


def get_incident_view(session: SessionDep) -> IncidentViewService:
    return IncidentViewService(session)


def get_approval_service(session: SessionDep) -> ApprovalService:
    return ApprovalService(session)


def get_simulation_service(session: SessionDep) -> SimulationService:
    return SimulationService(session)


def get_outcome_service(session: SessionDep) -> OutcomeService:
    return OutcomeService(session)


def get_connection_manager() -> ConnectionManager:
    return connection_manager


AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
WorkflowServiceDep = Annotated[WorkflowService, Depends(get_workflow_service)]
IncidentViewDep = Annotated[IncidentViewService, Depends(get_incident_view)]
ApprovalServiceDep = Annotated[ApprovalService, Depends(get_approval_service)]
SimulationServiceDep = Annotated[SimulationService, Depends(get_simulation_service)]
OutcomeServiceDep = Annotated[OutcomeService, Depends(get_outcome_service)]
ConnectionManagerDep = Annotated[ConnectionManager, Depends(get_connection_manager)]

IncidentIdPath = Annotated[uuid.UUID, Path(description="Incident UUID.")]


async def get_incident(incident_id: IncidentIdPath, view: IncidentViewDep) -> Incident:
    """Load the incident named in the path, 404ing if it does not exist."""
    return await view.require(incident_id)


IncidentDep = Annotated[Incident, Depends(get_incident)]
