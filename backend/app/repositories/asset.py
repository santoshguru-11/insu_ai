"""Asset persistence."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Select, func, select

from app.models.asset import Asset
from app.models.enums import AssetStatus, Criticality
from app.repositories.base import BaseRepository


class AssetRepository(BaseRepository[Asset]):
    model = Asset

    async def get_by_code(self, asset_code: str) -> Asset | None:
        result = await self.session.execute(select(Asset).where(Asset.asset_code == asset_code))
        return result.scalar_one_or_none()

    def _filtered(
        self,
        *,
        criticality: Criticality | None = None,
        status: AssetStatus | None = None,
        plant_name: str | None = None,
    ) -> Select[tuple[Asset]]:
        stmt = select(Asset)
        if criticality is not None:
            stmt = stmt.where(Asset.criticality == criticality)
        if status is not None:
            stmt = stmt.where(Asset.status == status)
        if plant_name is not None:
            stmt = stmt.where(Asset.plant_name == plant_name)
        return stmt

    async def list_filtered(
        self,
        *,
        criticality: Criticality | None = None,
        status: AssetStatus | None = None,
        plant_name: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Asset]:
        stmt = (
            self._filtered(criticality=criticality, status=status, plant_name=plant_name)
            .order_by(Asset.asset_code)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_filtered(
        self,
        *,
        criticality: Criticality | None = None,
        status: AssetStatus | None = None,
        plant_name: str | None = None,
    ) -> int:
        stmt = self._filtered(
            criticality=criticality, status=status, plant_name=plant_name
        ).with_only_columns(func.count(Asset.id))
        result = await self.session.execute(stmt)
        return int(result.scalar_one())
