"""Human approval gate in front of irreversible maintenance actions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ApprovalDecisionType, pg_enum

if TYPE_CHECKING:
    from app.models.incident import Incident
    from app.models.maintenance import MaintenanceProposal


class ApprovalDecision(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "approval_decisions"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("maintenance_proposals.id", ondelete="CASCADE"),
        nullable=False,
    )
    decision: Mapped[ApprovalDecisionType] = mapped_column(
        pg_enum(ApprovalDecisionType, "approval_decision_type"),
        nullable=False,
        default=ApprovalDecisionType.PENDING,
    )
    approver_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approver_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Only the hash of the single-use approval token is persisted; the token
    # itself is handed to the approver and never stored.
    approval_token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    incident: Mapped[Incident] = relationship(back_populates="approval_decisions")
    proposal: Mapped[MaintenanceProposal] = relationship(back_populates="approval_decisions")

    __table_args__ = (
        Index("ix_approval_decisions_decision", "decision"),
        Index("ix_approval_decisions_incident_id", "incident_id"),
        Index("ix_approval_decisions_proposal_id", "proposal_id"),
        Index("ix_approval_decisions_incident_id_decision", "incident_id", "decision"),
        Index("ix_approval_decisions_token_expires_at", "token_expires_at"),
    )
