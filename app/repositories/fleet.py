from __future__ import annotations

from datetime import date

from sqlalchemy import func, or_, select
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
        cost_center: str | None = None,
        competence: date | None = None,
    ) -> list[Vehicle]:
        stmt = select(Vehicle).where(Vehicle.deleted_at.is_(None))
        if not include_inactive:
            stmt = stmt.where(Vehicle.is_active.is_(True))
        # Filtro por Centro de Custo do projeto (aba Veículos): TEMPORAL com `competence`
        # (histórico) — veículo aparece se o centro VIGENTE == cc OU sem centro. Sem
        # `competence`, usa o cache. Sem `cost_center`, todos (compat).
        cc = (cost_center or "").strip()
        if cc:
            from app.services.cost_center_history_service import (
                vehicle_effective_cost_center_subquery,
            )

            eff_cc = (
                vehicle_effective_cost_center_subquery(competence)
                if competence is not None
                else Vehicle.cost_center
            )
            stmt = stmt.where(or_(func.lower(eff_cc) == cc.lower(), eff_cc.is_(None)))
        stmt = stmt.order_by(Vehicle.plate).offset(offset).limit(limit)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def list_active(self, *, offset: int = 0, limit: int = 200) -> list[Vehicle]:
        return await self.list_ordered(offset=offset, limit=limit, include_inactive=False)


class VehicleUsageRepository(Repository[VehicleUsage]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, VehicleUsage)

