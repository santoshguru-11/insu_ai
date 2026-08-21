"""Maintenance proposal, part check, work order and technician outcome contracts."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import (
    PartCheckStatus,
    ProductionImpact,
    ProposalStatus,
    WorkOrderStatus,
)
from app.schemas.common import ORMModel


class PartCheckRead(ORMModel):
    id: uuid.UUID
    sku: str = Field(examples=["BRG-6220-C3"])
    quantity: int = Field(ge=1, examples=[1])
    in_stock: bool | None = None
    location: str | None = Field(default=None, examples=["STORE-A"])
    lead_time_days: int | None = Field(default=None, examples=[0])
    estimated_cost: Decimal | None = Field(default=None, examples=[840])
    currency: str | None = Field(default=None, max_length=3, examples=["INR"])
    status: PartCheckStatus
    reserved_at: datetime | None = Field(
        default=None, description="Set only after an approval authorised the reservation."
    )
    created_at: datetime
    updated_at: datetime


class MaintenanceProposalRead(ORMModel):
    id: uuid.UUID
    incident_id: uuid.UUID
    proposed_start_at: datetime
    proposed_end_at: datetime | None = None
    duration_hours: float = Field(gt=0, examples=[6.0])
    rul_margin_days: float | None = Field(
        default=None,
        description="Days of remaining useful life still left if the work happens as proposed.",
        examples=[9.0],
    )
    production_impact: ProductionImpact
    crew_available: bool
    planned_changeover: bool = Field(
        description="True when the window rides an already-planned line changeover."
    )
    status: ProposalStatus
    part_checks: list[PartCheckRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class WorkOrderRead(ORMModel):
    id: uuid.UUID
    incident_id: uuid.UUID
    external_reference: str | None = Field(default=None, examples=["WO-40219"])
    status: WorkOrderStatus
    created_by: str | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class TechnicianOutcomeCreate(BaseModel):
    """What the technician reports back after doing the work."""

    technician_id: str = Field(max_length=128, examples=["tech-001"])
    technician_name: str = Field(max_length=255, examples=["R. Kumar"])
    diagnosis_confirmed: bool = Field(examples=[True])
    actual_finding: str = Field(examples=["Outer-race bearing wear with visible spalling"])
    parts_used: list[str] = Field(default_factory=list, examples=[["BRG-6220-C3"]])
    technician_note: str | None = Field(
        default=None, examples=["Bearing replaced during planned changeover."]
    )
    repair_duration_hours: float | None = Field(default=None, gt=0, examples=[4.5])


class TechnicianOutcomeRead(ORMModel):
    id: uuid.UUID
    work_order_id: uuid.UUID
    technician_id: str | None = None
    technician_name: str | None = None
    diagnosis_confirmed: bool | None = None
    actual_finding: str | None = None
    parts_used_json: list[dict[str, Any]] | list[str] = Field(default_factory=list)
    technician_note: str | None = None
    repair_duration_hours: float | None = None
    captured_at: datetime
    created_at: datetime
    updated_at: datetime
