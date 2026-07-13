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
        competence: date | None = None,
    ) -> list[Employee]:
        stmt = select(Employee)
        if search is not None:
            q = str(search).strip()
            if q:
                stmt = stmt.where(Employee.full_name.ilike(f"%{q}%"))
        # Filtro por Centro de Custo (Projetos → Custos → Mão de Obra): quando informado,
        # mostra apenas colaboradores do MESMO centro OU compartilhados
        # (can_allocate_other_cost_centers) OU sem centro (legado/não classificado).
        #
        # TEMPORAL: com `competence`, o centro do colaborador é resolvido POR COMPETÊNCIA a
        # partir do histórico (subquery correlata — 1 query, sem N+1, paginação no banco).
        # Sem `competence`, cai no cache `employees.cost_center` (compatibilidade).
        cc = (cost_center or "").strip()
        if cc:
            from app.services.cost_center_history_service import (
                employee_effective_cost_center_subquery,
            )

            eff_cc = (
                employee_effective_cost_center_subquery(competence)
                if competence is not None
                else Employee.cost_center
            )
            stmt = stmt.where(
                or_(
                    func.lower(eff_cc) == cc.lower(),
                    Employee.can_allocate_other_cost_centers.is_(True),
                    eff_cc.is_(None),
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

