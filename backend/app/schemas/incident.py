"""Incident contracts — list rows, full detail, and the transition envelope."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import ActorType, ScenarioType, Severity, WorkflowStatus
from app.schemas.approval import ApprovalDecisionRead, ApprovalTokenRead
from app.schemas.asset import AssetRead
from app.schemas.audit import AuditEventRead
from app.schemas.common import ORMModel
from app.schemas.diagnosis import (
    AgentRunRead,
    DiagnosisRead,
    DiagnosisSummary,
    RULEstimate,
    SentinelAnomalyRead,
)
from app.schemas.maintenance import (
    MaintenanceProposalRead,
    TechnicianOutcomeRead,
    WorkOrderRead,
)


class IncidentCreate(BaseModel):
    asset_id: uuid.UUID
    trace_id: str = Field(max_length=64, examples=["tr_9f21"])
    severity: Severity = Severity.ISO_20816_3_BAND_B
    workflow_status: WorkflowStatus = WorkflowStatus.WATCH
    scenario_type: ScenarioType = ScenarioType.NORMAL
    cloud_available: bool = True
    detected_at: datetime | None = None


class IncidentUpdate(BaseModel):
    severity: Severity | None = None
    resolved_at: datetime | None = None
    human_review_reason: str | None = None


class IncidentListItem(ORMModel):
    """One row of the incident list."""

    id: uuid.UUID
    trace_id: str = Field(examples=["tr_9f21"])
    asset_id: uuid.UUID
    asset_name: str = Field(examples=["Calender Roll Drive Train"])
    asset_code: str = Field(examples=["CAL-04-DRIVE"])
    workflow_status: WorkflowStatus
    severity: Severity
    scenario_type: ScenarioType
    cloud_available: bool
    diagnosis: DiagnosisSummary | None = Field(
        default=None, description="Latest diagnosis, if one exists yet."
    )
    rul: RULEstimate | None = None
    detected_at: datetime
    resolved_at: datetime | None = None
    updated_at: datetime


class IncidentDetail(ORMModel):
    """Everything the console needs to render one incident."""

    id: uuid.UUID
    trace_id: str
    workflow_status: WorkflowStatus
    severity: Severity
    scenario_type: ScenarioType
    cloud_available: bool = Field(
        description="False blocks every cloud-dependent action for this incident."
    )
    human_review_reason: str | None = None
    detected_at: datetime
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    asset: AssetRead
    anomalies: list[SentinelAnomalyRead] = Field(default_factory=list)
    agent_runs: list[AgentRunRead] = Field(default_factory=list)
    diagnosis: DiagnosisRead | None = None
    rul: RULEstimate | None = None
    proposal: MaintenanceProposalRead | None = None
    approval: ApprovalDecisionRead | None = Field(
        default=None, description="Most recent approval decision, if any."
    )
    work_order: WorkOrderRead | None = None
    technician_outcome: TechnicianOutcomeRead | None = None


class SimulateNextStepRequest(BaseModel):
    """Ask the guided demo to take the next legal step."""

    actor_id: str = Field(default="demo-user", max_length=128, examples=["demo-user"])
    actor_type: ActorType = Field(default=ActorType.SYSTEM, examples=[ActorType.SYSTEM])
    reason: str | None = Field(default=None, max_length=2000, examples=["Advance guided demo"])


class SimulateNextStepResponse(BaseModel):
    previous_state: WorkflowStatus
    workflow_status: WorkflowStatus
    advanced: bool = Field(
        description="False when the incident is parked and needs a human, or is finished."
    )
    detail: str = Field(description="Human-readable account of what the step did.")
    changed_records: dict[str, list[uuid.UUID]] = Field(
        default_factory=dict,
        description="Records created or updated by this step, keyed by table name.",
    )
    audit_event_ids: list[uuid.UUID] = Field(default_factory=list)
    incident: IncidentDetail


class ApprovalResponse(BaseModel):
    """Result of approving an incident: decision, token metadata, and the work order."""

    decision: ApprovalDecisionRead
    token: ApprovalTokenRead
    work_order_reference: str | None = Field(default=None, examples=["WO-40219"])
    audit_event_ids: list[uuid.UUID] = Field(default_factory=list)
    incident: IncidentDetail


class RejectionResponse(BaseModel):
    """Result of rejecting an incident. No reservation, no work order."""

    decision: ApprovalDecisionRead
    audit_event_ids: list[uuid.UUID] = Field(default_factory=list)
    incident: IncidentDetail


class OutcomeResponse(BaseModel):
    outcome: TechnicianOutcomeRead
    work_order: WorkOrderRead
    audit_event_ids: list[uuid.UUID] = Field(default_factory=list)
    incident: IncidentDetail


class AuditTimeline(BaseModel):
    """Chronological audit trail for one incident."""

    items: list[AuditEventRead]
    total: int
    limit: int
    offset: int
