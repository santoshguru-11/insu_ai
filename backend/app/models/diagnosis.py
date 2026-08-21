"""Agent-produced failure-mode diagnoses and the evidence supporting them."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import EvidenceType, pg_enum

if TYPE_CHECKING:
    from app.models.agent_run import AgentRun
    from app.models.incident import Incident


class Diagnosis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "diagnoses"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    failure_mode_code: Mapped[str] = mapped_column(String(64), nullable=False)
    fmea_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    # Remaining useful life, with the bounds of the estimate's confidence interval.
    rul_estimate_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    rul_ci_low_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    rul_ci_high_days: Mapped[float | None] = mapped_column(Float, nullable=True)

    incident: Mapped[Incident] = relationship(back_populates="diagnoses")
    agent_run: Mapped[AgentRun] = relationship(back_populates="diagnoses")
    evidence_items: Mapped[list[EvidenceItem]] = relationship(
        back_populates="diagnosis", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint(
            "rul_ci_low_days IS NULL OR rul_ci_high_days IS NULL "
            "OR rul_ci_low_days <= rul_ci_high_days",
            name="rul_ci_bounds",
        ),
        Index("ix_diagnoses_incident_id", "incident_id"),
        Index("ix_diagnoses_agent_run_id", "agent_run_id"),
        Index("ix_diagnoses_failure_mode_code", "failure_mode_code"),
    )


class EvidenceItem(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A single observation cited by a diagnosis (append-only in practice)."""

    __tablename__ = "evidence_items"

    diagnosis_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("diagnoses.id", ondelete="CASCADE"),
        nullable=False,
    )
    signal_name: Mapped[str] = mapped_column(String(128), nullable=False)
    observed_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    evidence_type: Mapped[EvidenceType] = mapped_column(
        pg_enum(EvidenceType, "evidence_type"),
        nullable=False,
    )
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(512), nullable=True)

    diagnosis: Mapped[Diagnosis] = relationship(back_populates="evidence_items")

    __table_args__ = (
        CheckConstraint("weight IS NULL OR (weight >= 0 AND weight <= 1)", name="weight_range"),
        Index("ix_evidence_items_diagnosis_id", "diagnosis_id"),
        Index("ix_evidence_items_signal_name", "signal_name"),
    )
