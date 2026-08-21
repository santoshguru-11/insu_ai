"""Asset contracts."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import AssetStatus, Criticality, Severity, WorkflowStatus
from app.schemas.common import ORMModel


class AssetBase(BaseModel):
    asset_code: str = Field(max_length=64, examples=["CAL-04-DRIVE"])
    name: str = Field(max_length=255, examples=["Calender Roll Drive Train"])
    plant_name: str = Field(max_length=255, examples=["Battery Plant"])
    line_name: str = Field(max_length=255, examples=["Calender Line 2"])
    criticality: Criticality = Criticality.MEDIUM
    status: AssetStatus = AssetStatus.OPERATIONAL


class AssetCreate(AssetBase):
    pass


class AssetUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    plant_name: str | None = Field(default=None, max_length=255)
    line_name: str | None = Field(default=None, max_length=255)
    criticality: Criticality | None = None
    status: AssetStatus | None = None


class AssetRead(ORMModel, AssetBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class LatestIncidentSummary(ORMModel):
    """Just enough of the newest incident to headline an asset detail page."""

    id: uuid.UUID
    trace_id: str
    workflow_status: WorkflowStatus
    severity: Severity
    detected_at: datetime
    resolved_at: datetime | None = None


class AssetDetail(AssetRead):
    latest_incident: LatestIncidentSummary | None = Field(
        default=None, description="Most recently detected incident, by detection time."
    )
    open_incident_count: int = Field(
        default=0, description="Incidents not yet in the resolved state."
    )
