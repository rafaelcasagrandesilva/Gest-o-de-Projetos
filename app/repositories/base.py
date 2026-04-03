from __future__ import annotations

from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import Base


ModelT = TypeVar("ModelT", bound=Base)


class Repository(Generic[ModelT]):
    def __init__(self, session: AsyncSession, model: type[ModelT]):
        self.session = session
        self.model = model

    async def get(self, entity_id: UUID) -> ModelT | None:
        stmt = select(self.model).where(self.model.id == entity_id)  # type: ignore[attr-defined]
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list(self, *, offset: int = 0, limit: int = 50) -> list[ModelT]:
        stmt = select(self.model).offset(offset).limit(limit)  # type: ignore[arg-type]
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def add(self, obj: ModelT) -> ModelT:
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self.session.delete(obj)

    def apply_updates(self, obj: ModelT, data: dict[str, Any]) -> ModelT:
        for k, v in data.items():
            if v is None:
                continue
            setattr(obj, k, v)
        return obj

