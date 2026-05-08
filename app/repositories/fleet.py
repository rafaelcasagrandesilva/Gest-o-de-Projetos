from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fleet import Vehicle, VehicleUsage
from app.repositories.base import Repository


class VehicleRepository(Repository[Vehicle]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Vehicle)

    async def list_ordered(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        include_inactive: bool = False,
    ) -> list[Vehicle]:
        stmt = (
            select(Vehicle)
            .where(Vehicle.deleted_at.is_(None))
            .order_by(Vehicle.plate)
            .offset(offset)
            .limit(limit)
        )
        if not include_inactive:
            stmt = stmt.where(Vehicle.is_active.is_(True))
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def list_active(self, *, offset: int = 0, limit: int = 200) -> list[Vehicle]:
        return await self.list_ordered(offset=offset, limit=limit, include_inactive=False)


class VehicleUsageRepository(Repository[VehicleUsage]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, VehicleUsage)

