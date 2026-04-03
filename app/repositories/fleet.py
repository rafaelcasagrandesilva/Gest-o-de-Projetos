from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fleet import Vehicle, VehicleUsage
from app.repositories.base import Repository


class VehicleRepository(Repository[Vehicle]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Vehicle)

    async def list_ordered(
        self, *, offset: int = 0, limit: int = 50, active_only: bool = False
    ) -> list[Vehicle]:
        stmt = select(Vehicle).order_by(Vehicle.plate).offset(offset).limit(limit)
        if active_only:
            stmt = stmt.where(Vehicle.is_active.is_(True))
        res = await self.session.execute(stmt)
        return list(res.scalars().all())


class VehicleUsageRepository(Repository[VehicleUsage]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, VehicleUsage)

