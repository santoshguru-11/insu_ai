"""Append-only audit trail.

Rows in `audit_events` are written once and never touched again. Two things
enforce that:

* the repository layer (`app.repositories.audit_event`) exposes no update or
  delete method, and
* a database trigger installed by the initial migration raises on any UPDATE or
  DELETE against the table — so even a stray `psql` session cannot rewrite it.

Because the trigger blocks deletes, the `incident_id` foreign key uses
``ON DELETE RESTRICT``: an incident that has audit events cannot be removed.
`trace_id` is therefore the durable correlator to query the trail by.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import ActorType, pg_enum

AUDIT_GUARD_FUNCTION = "reject_audit_event_mutation"
AUDIT_GUARD_TRIGGER = "trg_audit_events_append_only"


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_events"

    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="RESTRICT"),
        nullable=True,
    )
    actor_type: Mapped[ActorType] = mapped_column(
        pg_enum(ActorType, "actor_type"),
        nullable=False,
    )
    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    event_payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # No `updated_at`: the row is immutable, so there is nothing to update.

    __table_args__ = (
        Index("ix_audit_events_trace_id", "trace_id"),
        Index("ix_audit_events_incident_id", "incident_id"),
        Index("ix_audit_events_occurred_at", "occurred_at"),
        Index("ix_audit_events_event_type", "event_type"),
        Index("ix_audit_events_trace_id_occurred_at", "trace_id", "occurred_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<AuditEvent {self.event_type} trace={self.trace_id}>"
