"""Asset persistence."""

from __future__ import annotations

from sqlalchemy import select

from app.models.asset import Asset
from app.repositories.base import BaseRepository


class AssetRepository(BaseRepository[Asset]):
    model = Asset

    async def get_by_code(self, asset_code: str) -> Asset | None:
        result = await self.session.execute(select(Asset).where(Asset.asset_code == asset_code))
        return result.scalar_one_or_none()
