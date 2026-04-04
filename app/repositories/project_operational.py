from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fleet import Vehicle
from app.core.scenario import coerce_scenario, scenario_pg_rhs
from app.models.project_operational import ProjectLabor, ProjectOperationalFixed, ProjectSystemCost, ProjectVehicle
from app.repositories.base import Repository
from app.utils.date_utils import normalize_competencia


class ProjectLaborRepository(Repository[ProjectLabor]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ProjectLabor)

    async def get_with_employee(self, labor_id: UUID) -> ProjectLabor | None:
        stmt = (
            select(ProjectLabor)
            .options(selectinload(ProjectLabor.employee))
            .where(ProjectLabor.id == labor_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_project_employee_competencia(
        self, *, project_id: UUID, employee_id: UUID, competencia: date, scenario: str | None = None
    ) -> ProjectLabor | None:
        eff = coerce_scenario(scenario)
        competencia = normalize_competencia(competencia)
        stmt = select(ProjectLabor).where(
            ProjectLabor.project_id == project_id,
            ProjectLabor.employee_id == employee_id,
            ProjectLabor.competencia == competencia,
            ProjectLabor.scenario == scenario_pg_rhs(eff),
        )
        result = await self.session.execute(stmt)
        return result.scalars().one_or_none()

    async def list_by_project(
        self,
        *,
        project_id: UUID,
        competencia: date,
        scenario: str | None = None,
        offset: int = 0,
        limit: int = 200,
    ) -> list[ProjectLabor]:
        eff = coerce_scenario(scenario)
        comp = normalize_competencia(competencia)
        stmt = (
            select(ProjectLabor)
            .options(selectinload(ProjectLabor.employee))
            .where(
                ProjectLabor.project_id == project_id,
                ProjectLabor.competencia == comp,
                ProjectLabor.scenario == scenario_pg_rhs(eff),
            )
            .order_by(ProjectLabor.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def list_by_competencia(
        self,
        *,
        competencia: date,
        scenario: str | None = None,
        project_id: UUID | None = None,
    ) -> list[ProjectLabor]:
        """Todas as alocações de mão de obra no mês/cenário; opcionalmente filtradas por projeto."""
        eff = coerce_scenario(scenario)
        comp = normalize_competencia(competencia)
        stmt = (
            select(ProjectLabor)
            .options(
                selectinload(ProjectLabor.employee),
                selectinload(ProjectLabor.project),
            )
            .where(
                ProjectLabor.competencia == comp,
                ProjectLabor.scenario == scenario_pg_rhs(eff),
            )
        )
        if project_id is not None:
            stmt = stmt.where(ProjectLabor.project_id == project_id)
        res = await self.session.execute(stmt)
        rows = list(res.scalars().all())
        rows.sort(
            key=lambda pl: (
                str(pl.employee_id),
                (pl.project.name if pl.project else "") or "",
            )
        )
        return rows

    async def sum_allocation_percentage_for_employee_competencia(
        self, *, employee_id: UUID, competencia: date, scenario: str | None = None
    ) -> float:
        eff = coerce_scenario(scenario)
        comp = normalize_competencia(competencia)
        stmt = select(func.coalesce(func.sum(ProjectLabor.allocation_percentage), 0)).where(
            ProjectLabor.employee_id == employee_id,
            ProjectLabor.competencia == comp,
            ProjectLabor.scenario == scenario_pg_rhs(eff),
        )
        v = (await self.session.execute(stmt)).scalar_one()
        return float(v)


class ProjectVehicleRepository(Repository[ProjectVehicle]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ProjectVehicle)

    async def get_with_vehicle_and_driver(self, allocation_id: UUID) -> ProjectVehicle | None:
        stmt = (
            select(ProjectVehicle)
            .options(selectinload(ProjectVehicle.vehicle).selectinload(Vehicle.driver))
            .where(ProjectVehicle.id == allocation_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_project_fleet_vehicle_competencia(
        self, *, project_id: UUID, vehicle_id: UUID, competencia: date, scenario: str | None = None
    ) -> ProjectVehicle | None:
        eff = coerce_scenario(scenario)
        comp = normalize_competencia(competencia)
        stmt = select(ProjectVehicle).where(
            ProjectVehicle.project_id == project_id,
            ProjectVehicle.vehicle_id == vehicle_id,
            ProjectVehicle.competencia == comp,
            ProjectVehicle.scenario == scenario_pg_rhs(eff),
        )
        return (await self.session.execute(stmt)).scalars().one_or_none()

    async def list_by_project(
        self,
        *,
        project_id: UUID,
        competencia: date,
        scenario: str | None = None,
        offset: int = 0,
        limit: int = 200,
    ) -> list[ProjectVehicle]:
        eff = coerce_scenario(scenario)
        comp = normalize_competencia(competencia)
        stmt = (
            select(ProjectVehicle)
            .options(selectinload(ProjectVehicle.vehicle).selectinload(Vehicle.driver))
            .where(
                ProjectVehicle.project_id == project_id,
                ProjectVehicle.competencia == comp,
                ProjectVehicle.scenario == scenario_pg_rhs(eff),
            )
            .order_by(ProjectVehicle.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())


class ProjectSystemCostRepository(Repository[ProjectSystemCost]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ProjectSystemCost)

    async def list_by_project(
        self,
        *,
        project_id: UUID,
        competencia: date,
        scenario: str | None = None,
        offset: int = 0,
        limit: int = 200,
    ) -> list[ProjectSystemCost]:
        eff = coerce_scenario(scenario)
        stmt = (
            select(ProjectSystemCost)
            .where(
                ProjectSystemCost.project_id == project_id,
                ProjectSystemCost.competencia == competencia,
                ProjectSystemCost.scenario == scenario_pg_rhs(eff),
            )
            .order_by(ProjectSystemCost.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())


class ProjectOperationalFixedRepository(Repository[ProjectOperationalFixed]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ProjectOperationalFixed)

    async def list_by_project(
        self,
        *,
        project_id: UUID,
        competencia: date,
        scenario: str | None = None,
        offset: int = 0,
        limit: int = 200,
    ) -> list[ProjectOperationalFixed]:
        eff = coerce_scenario(scenario)
        stmt = (
            select(ProjectOperationalFixed)
            .where(
                ProjectOperationalFixed.project_id == project_id,
                ProjectOperationalFixed.competencia == competencia,
                ProjectOperationalFixed.scenario == scenario_pg_rhs(eff),
            )
            .order_by(ProjectOperationalFixed.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())
