"""Proposed maintenance windows and the spare-part checks behind them."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import PartCheckStatus, ProductionImpact, ProposalStatus, pg_enum

if TYPE_CHECKING:
    from app.models.approval import ApprovalDecision
    from app.models.incident import Incident


class MaintenanceProposal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "maintenance_proposals"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    proposed_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_hours: Mapped[float] = mapped_column(Float, nullable=False)
    # Days of remaining useful life still left if the work happens as proposed.
    rul_margin_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    production_impact: Mapped[ProductionImpact] = mapped_column(
        pg_enum(ProductionImpact, "production_impact"),
        nullable=False,
        default=ProductionImpact.NONE,
    )
    crew_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[ProposalStatus] = mapped_column(
        pg_enum(ProposalStatus, "proposal_status"),
        nullable=False,
        default=ProposalStatus.DRAFT,
    )

    incident: Mapped[Incident] = relationship(back_populates="maintenance_proposals")
    part_checks: Mapped[list[PartCheck]] = relationship(
        back_populates="maintenance_proposal",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    approval_decisions: Mapped[list[ApprovalDecision]] = relationship(
        back_populates="proposal", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint("duration_hours > 0", name="duration_positive"),
        Index("ix_maintenance_proposals_incident_id", "incident_id"),
        Index("ix_maintenance_proposals_status", "status"),
        Index("ix_maintenance_proposals_proposed_start_at", "proposed_start_at"),
    )


class PartCheck(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Availability of one spare part required by a proposal."""

    __tablename__ = "part_checks"

    maintenance_proposal_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("maintenance_proposals.id", ondelete="CASCADE"),
        nullable=False,
    )
    sku: Mapped[str] = mapped_column(String(128), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    in_stock: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    status: Mapped[PartCheckStatus] = mapped_column(
        pg_enum(PartCheckStatus, "part_check_status"),
        nullable=False,
        default=PartCheckStatus.PENDING,
    )

    maintenance_proposal: Mapped[MaintenanceProposal] = relationship(back_populates="part_checks")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint(
            "lead_time_days IS NULL OR lead_time_days >= 0", name="lead_time_non_negative"
        ),
        Index("ix_part_checks_maintenance_proposal_id", "maintenance_proposal_id"),
        Index("ix_part_checks_sku", "sku"),
        Index("ix_part_checks_status", "status"),
    )
