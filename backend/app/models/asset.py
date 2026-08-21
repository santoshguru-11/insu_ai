"""Physical equipment monitored by the console."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AssetStatus, Criticality, pg_enum

if TYPE_CHECKING:
    from app.models.incident import Incident


class Asset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assets"

    asset_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    plant_name: Mapped[str] = mapped_column(String(255), nullable=False)
    line_name: Mapped[str] = mapped_column(String(255), nullable=False)
    criticality: Mapped[Criticality] = mapped_column(
        pg_enum(Criticality, "criticality"),
        nullable=False,
        default=Criticality.MEDIUM,
    )
    status: Mapped[AssetStatus] = mapped_column(
        pg_enum(AssetStatus, "asset_status"),
        nullable=False,
        default=AssetStatus.OPERATIONAL,
    )

    incidents: Mapped[list[Incident]] = relationship(
        back_populates="asset",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_assets_asset_code", "asset_code"),
        Index("ix_assets_plant_name_line_name", "plant_name", "line_name"),
        Index("ix_assets_status", "status"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<Asset {self.asset_code}>"
