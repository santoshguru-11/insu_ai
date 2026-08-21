"""Incident request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import Severity, WorkflowStatus
from app.schemas.common import ORMModel


class IncidentBase(BaseModel):
    asset_id: uuid.UUID
    trace_id: str = Field(max_length=64)
    severity: Severity = Severity.WARNING
    workflow_status: WorkflowStatus = WorkflowStatus.DETECTED


class IncidentCreate(IncidentBase):
    detected_at: datetime | None = None


class IncidentUpdate(BaseModel):
    severity: Severity | None = None
    workflow_status: WorkflowStatus | None = None
    resolved_at: datetime | None = None


class IncidentRead(ORMModel, IncidentBase):
    id: uuid.UUID
    detected_at: datetime
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime
