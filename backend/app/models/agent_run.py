"""One execution of a diagnostic agent against an incident."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import AgentKind, AgentRunStatus, pg_enum

if TYPE_CHECKING:
    from app.models.diagnosis import Diagnosis
    from app.models.incident import Incident


class AgentRun(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "agent_runs"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # Which stage of the pipeline this run belongs to.
    agent_kind: Mapped[AgentKind | None] = mapped_column(
        pg_enum(AgentKind, "agent_kind"), nullable=True
    )
    agent_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[AgentRunStatus] = mapped_column(
        pg_enum(AgentRunStatus, "agent_run_status"),
        nullable=False,
        default=AgentRunStatus.PENDING,
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    incident: Mapped[Incident] = relationship(back_populates="agent_runs")
    diagnoses: Mapped[list[Diagnosis]] = relationship(
        back_populates="agent_run", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
        Index("ix_agent_runs_incident_id", "incident_id"),
        Index("ix_agent_runs_status", "status"),
        Index("ix_agent_runs_agent_kind", "agent_kind"),
        Index("ix_agent_runs_started_at", "started_at"),
    )
