"""Work orders dispatched after approval, and what the technician found."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import WorkOrderStatus, pg_enum

if TYPE_CHECKING:
    from app.models.incident import Incident


class WorkOrder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "work_orders"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Identifier in the external CMMS/EAM. No integration exists yet; the
    # column is populated by whichever adapter creates the order.
    external_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[WorkOrderStatus] = mapped_column(
        pg_enum(WorkOrderStatus, "work_order_status"),
        nullable=False,
        default=WorkOrderStatus.DRAFT,
    )
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    incident: Mapped[Incident] = relationship(back_populates="work_orders")
    technician_outcomes: Mapped[list[TechnicianOutcome]] = relationship(
        back_populates="work_order", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        Index("ix_work_orders_incident_id", "incident_id"),
        Index("ix_work_orders_status", "status"),
        Index("ix_work_orders_external_reference", "external_reference"),
    )


class TechnicianOutcome(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Ground truth reported back from the shop floor — the AI feedback loop."""

    __tablename__ = "technician_outcomes"

    work_order_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("work_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    technician_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    technician_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    diagnosis_confirmed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    actual_finding: Mapped[str | None] = mapped_column(Text, nullable=True)
    parts_used_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    technician_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    repair_duration_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    work_order: Mapped[WorkOrder] = relationship(back_populates="technician_outcomes")

    __table_args__ = (
        Index("ix_technician_outcomes_work_order_id", "work_order_id"),
        Index("ix_technician_outcomes_captured_at", "captured_at"),
        Index("ix_technician_outcomes_diagnosis_confirmed", "diagnosis_confirmed"),
    )
