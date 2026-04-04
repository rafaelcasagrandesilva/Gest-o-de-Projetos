from __future__ import annotations

import calendar
from datetime import date
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scenario import coerce_scenario, scenario_pg_rhs
from app.models.employee import Employee, EmployeeAllocation
from app.repositories.base import Repository
from app.utils.date_utils import normalize_competencia


class EmployeeRepository(Repository[Employee]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Employee)

    async def list_active_ordered(self, *, limit: int = 10_000) -> list[Employee]:
        stmt = (
            select(Employee)
            .where(Employee.is_active)
            .order_by(Employee.full_name.asc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())


class EmployeeAllocationRepository(Repository[EmployeeAllocation]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, EmployeeAllocation)

    async def list_by_project(
        self,
        *,
        project_id: UUID,
        scenario: str | None = None,
        competencia: date | None = None,
    ) -> list[EmployeeAllocation]:
        eff = coerce_scenario(scenario)
        stmt = (
            select(EmployeeAllocation)
            .where(
                EmployeeAllocation.project_id == project_id,
                EmployeeAllocation.scenario == scenario_pg_rhs(eff),
            )
            .order_by(EmployeeAllocation.start_date.desc())
        )
        if competencia is not None:
            comp = normalize_competencia(competencia)
            _, last = calendar.monthrange(comp.year, comp.month)
            month_end = date(comp.year, comp.month, last)
            stmt = stmt.where(
                EmployeeAllocation.start_date <= month_end,
                or_(EmployeeAllocation.end_date.is_(None), EmployeeAllocation.end_date >= comp),
            )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

