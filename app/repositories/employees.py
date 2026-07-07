from __future__ import annotations

import calendar
from datetime import date
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scenario import coerce_scenario, scenario_pg_rhs
from app.models.employee import Employee, EmployeeAllocation
from app.repositories.base import Repository
from app.utils.date_utils import normalize_competencia


class EmployeeRepository(Repository[Employee]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Employee)

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        search: str | None = None,
        cost_center: str | None = None,
    ) -> list[Employee]:
        stmt = select(Employee)
        if search is not None:
            q = str(search).strip()
            if q:
                stmt = stmt.where(Employee.full_name.ilike(f"%{q}%"))
        # Filtro por Centro de Custo (Projetos → Custos → Mão de Obra): quando informado,
        # mostra apenas colaboradores do MESMO centro OU marcados como compartilhados
        # (can_allocate_other_cost_centers). Sem o filtro, comportamento inalterado.
        cc = (cost_center or "").strip()
        if cc:
            stmt = stmt.where(
                or_(
                    func.lower(Employee.cost_center) == cc.lower(),
                    Employee.can_allocate_other_cost_centers.is_(True),
                    # Não classificado (legado sem cost_center) permanece visível — o filtro
                    # se estreita naturalmente conforme os colaboradores são classificados,
                    # sem quebrar a alocação de quem ainda não tem Centro de Custo.
                    Employee.cost_center.is_(None),
                )
            )
        stmt = stmt.order_by(Employee.full_name.asc()).offset(offset).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

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

