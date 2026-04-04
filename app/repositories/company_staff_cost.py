from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.scenario import coerce_scenario, scenario_pg_rhs
from app.models.company_staff_cost import CompanyStaffCost
from app.repositories.base import Repository
from app.utils.date_utils import normalize_competencia


class CompanyStaffCostRepository(Repository[CompanyStaffCost]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, CompanyStaffCost)

    async def get_with_employee(self, entity_id: UUID) -> CompanyStaffCost | None:
        stmt = (
            select(CompanyStaffCost)
            .options(selectinload(CompanyStaffCost.employee))
            .where(CompanyStaffCost.id == entity_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_by_competencia_scenario(
        self, *, competencia: date, scenario: str | None = None
    ) -> list[CompanyStaffCost]:
        eff = coerce_scenario(scenario)
        comp = normalize_competencia(competencia)
        stmt = (
            select(CompanyStaffCost)
            .options(selectinload(CompanyStaffCost.employee))
            .where(
                CompanyStaffCost.competencia == comp,
                CompanyStaffCost.scenario == scenario_pg_rhs(eff),
            )
            .order_by(CompanyStaffCost.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_by_employee_competencia_scenario(
        self, *, employee_id: UUID, competencia: date, scenario: str | None = None
    ) -> CompanyStaffCost | None:
        eff = coerce_scenario(scenario)
        comp = normalize_competencia(competencia)
        stmt = select(CompanyStaffCost).where(
            CompanyStaffCost.employee_id == employee_id,
            CompanyStaffCost.competencia == comp,
            CompanyStaffCost.scenario == scenario_pg_rhs(eff),
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()
