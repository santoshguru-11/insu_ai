"""The anomaly the Sentinel agent raises before any diagnosis exists.

Kept separate from `evidence_items`: evidence belongs to a diagnosis and is
cited in support of a conclusion, whereas an anomaly is the raw trigger that
opened the incident in the first place — it exists even when no diagnosis
follows (see the low-confidence and offline demo scenarios).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.incident import Incident


class SentinelAnomaly(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "sentinel_anomalies"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    signal_name: Mapped[str] = mapped_column(String(128), nullable=False)
    observed_value: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # How far the observation sits from the learned baseline.
    sigma_deviation: Mapped[float | None] = mapped_column(Float, nullable=True)
    thermal_delta_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Consecutive analysis windows the anomaly held for; a single-window spike
    # is noise, a persistent one is a real change in machine condition.
    window_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    persisted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    incident: Mapped[Incident] = relationship(back_populates="sentinel_anomalies")

    __table_args__ = (
        Index("ix_sentinel_anomalies_incident_id", "incident_id"),
        Index("ix_sentinel_anomalies_detected_at", "detected_at"),
    )
