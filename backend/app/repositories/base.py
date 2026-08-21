"""Generic async repository.

Repositories own all SQL. Services call them; route handlers never build
queries directly. Nothing here commits — the request-scoped session dependency
does that once, so a handler's writes stay in one transaction.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base


class ReadOnlyRepository[ModelT: Base]:
    """Read and create access — no update, no delete."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, entity_id: uuid.UUID) -> ModelT | None:
        return await self.session.get(self.model, entity_id)

    async def list(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        **filters: Any,
    ) -> Sequence[ModelT]:
        stmt = select(self.model).limit(limit).offset(offset)
        stmt = self._apply_filters(stmt, filters)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self, **filters: Any) -> int:
        stmt = select(func.count()).select_from(self.model)
        stmt = self._apply_filters(stmt, filters)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    def _apply_filters(self, stmt: Any, filters: dict[str, Any]) -> Any:
        for field, value in filters.items():
            if value is None:
                continue
            stmt = stmt.where(getattr(self.model, field) == value)
        return stmt


class BaseRepository[ModelT: Base](ReadOnlyRepository[ModelT]):
    """Full CRUD access, for the mutable tables."""

    async def update(self, entity: ModelT, **values: Any) -> ModelT:
        for field, value in values.items():
            if value is not None:
                setattr(entity, field, value)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def delete(self, entity: ModelT) -> None:
        await self.session.delete(entity)
        await self.session.flush()

    async def delete_by_id(self, entity_id: uuid.UUID) -> int:
        result = await self.session.execute(
            delete(self.model).where(self.model.id == entity_id)  # type: ignore[attr-defined]
        )
        await self.session.flush()
        return int(result.rowcount or 0)
