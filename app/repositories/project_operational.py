from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fleet import Vehicle
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
        self, *, project_id: UUID, employee_id: UUID, competencia: date
    ) -> ProjectLabor | None:
        competencia = normalize_competencia(competencia)
        stmt = select(ProjectLabor).where(
            ProjectLabor.project_id == project_id,
            ProjectLabor.employee_id == employee_id,
            ProjectLabor.competencia == competencia,
        )
        result = await self.session.execute(stmt)
        return result.scalars().one_or_none()

    async def list_by_project(
        self, *, project_id: UUID, competencia: date, offset: int = 0, limit: int = 200
    ) -> list[ProjectLabor]:
        comp = normalize_competencia(competencia)
        stmt = (
            select(ProjectLabor)
            .options(selectinload(ProjectLabor.employee))
            .where(
                ProjectLabor.project_id == project_id,
                ProjectLabor.competencia == comp,
            )
            .order_by(ProjectLabor.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def sum_allocation_percentage_for_employee_competencia(
        self, *, employee_id: UUID, competencia: date
    ) -> float:
        comp = normalize_competencia(competencia)
        stmt = select(func.coalesce(func.sum(ProjectLabor.allocation_percentage), 0)).where(
            ProjectLabor.employee_id == employee_id,
            ProjectLabor.competencia == comp,
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
        self, *, project_id: UUID, vehicle_id: UUID, competencia: date
    ) -> ProjectVehicle | None:
        comp = normalize_competencia(competencia)
        stmt = select(ProjectVehicle).where(
            ProjectVehicle.project_id == project_id,
            ProjectVehicle.vehicle_id == vehicle_id,
            ProjectVehicle.competencia == comp,
        )
        return (await self.session.execute(stmt)).scalars().one_or_none()

    async def list_by_project(
        self, *, project_id: UUID, competencia: date, offset: int = 0, limit: int = 200
    ) -> list[ProjectVehicle]:
        comp = normalize_competencia(competencia)
        stmt = (
            select(ProjectVehicle)
            .options(selectinload(ProjectVehicle.vehicle).selectinload(Vehicle.driver))
            .where(ProjectVehicle.project_id == project_id, ProjectVehicle.competencia == comp)
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
        self, *, project_id: UUID, competencia: date, offset: int = 0, limit: int = 200
    ) -> list[ProjectSystemCost]:
        stmt = (
            select(ProjectSystemCost)
            .where(ProjectSystemCost.project_id == project_id, ProjectSystemCost.competencia == competencia)
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
        self, *, project_id: UUID, competencia: date, offset: int = 0, limit: int = 200
    ) -> list[ProjectOperationalFixed]:
        stmt = (
            select(ProjectOperationalFixed)
            .where(
                ProjectOperationalFixed.project_id == project_id,
                ProjectOperationalFixed.competencia == competencia,
            )
            .order_by(ProjectOperationalFixed.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())
