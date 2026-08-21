"""An anomaly detected on an asset, tracked through the maintenance workflow."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import Severity, WorkflowStatus, pg_enum

if TYPE_CHECKING:
    from app.models.agent_run import AgentRun
    from app.models.approval import ApprovalDecision
    from app.models.asset import Asset
    from app.models.diagnosis import Diagnosis
    from app.models.maintenance import MaintenanceProposal
    from app.models.work_order import WorkOrder


class Incident(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "incidents"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Correlates every record produced while handling this incident, including
    # audit events written after the incident row itself is gone.
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    severity: Mapped[Severity] = mapped_column(
        pg_enum(Severity, "severity"),
        nullable=False,
        default=Severity.WARNING,
    )
    workflow_status: Mapped[WorkflowStatus] = mapped_column(
        pg_enum(WorkflowStatus, "workflow_status"),
        nullable=False,
        default=WorkflowStatus.DETECTED,
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    asset: Mapped[Asset] = relationship(back_populates="incidents")
    agent_runs: Mapped[list[AgentRun]] = relationship(
        back_populates="incident", cascade="all, delete-orphan", passive_deletes=True
    )
    diagnoses: Mapped[list[Diagnosis]] = relationship(
        back_populates="incident", cascade="all, delete-orphan", passive_deletes=True
    )
    maintenance_proposals: Mapped[list[MaintenanceProposal]] = relationship(
        back_populates="incident", cascade="all, delete-orphan", passive_deletes=True
    )
    approval_decisions: Mapped[list[ApprovalDecision]] = relationship(
        back_populates="incident", cascade="all, delete-orphan", passive_deletes=True
    )
    work_orders: Mapped[list[WorkOrder]] = relationship(
        back_populates="incident", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        Index("ix_incidents_workflow_status", "workflow_status"),
        Index("ix_incidents_asset_id", "asset_id"),
        Index("ix_incidents_trace_id", "trace_id"),
        Index("ix_incidents_detected_at", "detected_at"),
        Index("ix_incidents_severity", "severity"),
        # Supports the console's default view: open incidents on one asset, newest first.
        Index("ix_incidents_asset_id_workflow_status", "asset_id", "workflow_status"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<Incident {self.trace_id} {self.workflow_status}>"
