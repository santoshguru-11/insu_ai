"""Sentinel anomaly, agent run, diagnosis, evidence and RUL contracts."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import (
    AgentKind,
    AgentRunStatus,
    ConfidenceBand,
    EvidenceType,
    RecommendedAction,
)
from app.schemas.common import ORMModel


class SentinelAnomalyRead(ORMModel):
    """The raw deviation that opened the incident."""

    id: uuid.UUID
    signal_name: str = Field(examples=["bpfo_envelope_velocity"])
    observed_value: float = Field(examples=[4.2])
    baseline_value: float | None = Field(default=None, examples=[1.1])
    unit: str | None = Field(default=None, examples=["mm/s"])
    sigma_deviation: float | None = Field(
        default=None, description="Deviation from baseline, in sigma.", examples=[6.4]
    )
    thermal_delta_c: float | None = Field(default=None, examples=[14.8])
    window_count: int = Field(
        description="Consecutive analysis windows the anomaly held for.", examples=[6]
    )
    persisted: bool = Field(description="True when the anomaly is not a single-window spike.")
    detected_at: datetime
    created_at: datetime


class AgentRunRead(ORMModel):
    """One execution of a simulated agent."""

    id: uuid.UUID
    incident_id: uuid.UUID
    agent_id: str = Field(examples=["sentinel-agent"])
    agent_kind: AgentKind | None = None
    agent_version: str = Field(examples=["1.4.0"])
    model_name: str | None = Field(
        default=None,
        description="Recorded for provenance only; no model is invoked in this simulation.",
    )
    model_version: str | None = None
    status: AgentRunStatus
    confidence: float | None = Field(default=None, ge=0, le=1)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class EvidenceItemRead(ORMModel):
    """A signal cited in support of a diagnosis."""

    id: uuid.UUID
    signal_name: str
    observed_value: float | None = None
    baseline_value: float | None = None
    unit: str | None = None
    evidence_type: EvidenceType
    weight: float | None = Field(default=None, ge=0, le=1)
    source_reference: str | None = None
    created_at: datetime


class DiagnosisAlternativeRead(ORMModel):
    """A failure mode the agent considered and ruled out, with its reasoning."""

    id: uuid.UUID
    failure_mode_code: str = Field(examples=["MISALIGNMENT"])
    rejection_reason: str = Field(examples=["No 2x running-speed component present."])
    confidence: float | None = Field(default=None, ge=0, le=1)
    created_at: datetime


class RULEstimate(BaseModel):
    """Remaining useful life, with the bounds of its credible interval."""

    estimate_days: float | None = Field(default=None, examples=[18.0])
    ci_low_days: float | None = Field(default=None, examples=[12.0])
    ci_high_days: float | None = Field(default=None, examples=[26.0])

    @property
    def is_present(self) -> bool:
        return self.estimate_days is not None


class DiagnosisRead(ORMModel):
    id: uuid.UUID
    incident_id: uuid.UUID
    agent_run_id: uuid.UUID
    failure_mode_code: str = Field(examples=["BRG_OUTER_RACE_WEAR"])
    fmea_reference: str | None = Field(default=None, examples=["FM-1182"])
    confidence: float = Field(ge=0, le=1, examples=[0.87])
    confidence_band: ConfidenceBand
    recommended_action: RecommendedAction
    recommended_action_note: str | None = None
    similar_work_order_reference: str | None = Field(default=None, examples=["WO-40218"])
    rul: RULEstimate
    alternatives: list[DiagnosisAlternativeRead] = Field(default_factory=list)
    evidence_items: list[EvidenceItemRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class DiagnosisSummary(BaseModel):
    """Compact diagnosis view for incident list rows."""

    failure_mode_code: str
    confidence: float
    confidence_band: ConfidenceBand
    recommended_action: RecommendedAction
    fmea_reference: str | None = None
