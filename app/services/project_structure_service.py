from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_operational import ProjectLabor, ProjectOperationalFixed, ProjectSystemCost, ProjectVehicle
from app.repositories.employees import EmployeeRepository
from app.repositories.projects import ProjectRepository
from app.repositories.fleet import VehicleRepository as FleetVehicleRepository
from app.repositories.project_operational import (
    ProjectLaborRepository,
    ProjectOperationalFixedRepository,
    ProjectSystemCostRepository,
    ProjectVehicleRepository,
)
from app.schemas.project_structure import (
    LaborCostBreakdown,
    ProjectLaborDetailItem,
    ProjectLaborRead,
    ProjectVehicleRead,
)
from app.services.employee_cost_service import (
    calculate_clt_cost,
    calculate_pj_total_cost,
    clt_cost_breakdown,
    pj_cost_breakdown,
)
from app.services.operational_cost_calc import compute_vehicle_monthly_cost
from app.services.settings_service import SettingsService
from app.utils.date_utils import normalize_competencia

logger = logging.getLogger(__name__)

_PROJECT_LABOR_UNIQUE = "uq_project_labors_project_employee_competencia"


def _exception_chain(exc: IntegrityError) -> list[BaseException]:
    """Inclui SQLAlchemy IntegrityError, `.orig` (ex.: asyncpg) e __cause__."""
    out: list[BaseException] = []
    seen: set[int] = set()

    def walk(e: BaseException | None) -> None:
        while e is not None and id(e) not in seen:
            seen.add(id(e))
            out.append(e)
            e = getattr(e, "__cause__", None)

    walk(exc)
    orig = getattr(exc, "orig", None)
    if orig is not None:
        walk(orig)
    return out


def _sqlstate(o: BaseException) -> str | None:
    st = getattr(o, "sqlstate", None) or getattr(o, "pgcode", None)
    return str(st) if st is not None else None


def _project_labor_integrity_kind(exc: IntegrityError) -> Literal["unique", "fk", "not_null", "unknown"]:
    """INSERT só em project_labors: unique, FK ou NOT NULL (schema antigo)."""
    for o in _exception_chain(exc):
        mod = type(o).__module__
        name = type(o).__name__
        if mod.startswith("asyncpg") and name == "UniqueViolationError":
            return "unique"
        if mod.startswith("asyncpg") and name == "ForeignKeyViolationError":
            return "fk"
        if mod.startswith("asyncpg") and name == "NotNullViolationError":
            return "not_null"
        st = _sqlstate(o)
        if st == "23505":
            return "unique"
        if st == "23503":
            return "fk"
        if st == "23502":
            return "not_null"
    blob = " ".join(str(x) for x in _exception_chain(exc)).lower()
    if _PROJECT_LABOR_UNIQUE.lower() in blob:
        return "unique"
    if "unique" in blob and "project_labors" in blob:
        return "unique"
    if "foreign key" in blob:
        return "fk"
    return "unknown"


class ProjectStructureService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.labors = ProjectLaborRepository(session)
        self.vehicles = ProjectVehicleRepository(session)
        self.systems = ProjectSystemCostRepository(session)
        self.fixed = ProjectOperationalFixedRepository(session)
        self.employees = EmployeeRepository(session)

    async def _settings(self):
        return await SettingsService(self.session).get_or_create()

    # --- Labor (vínculo; custo derivado do Employee) ---

    async def list_labors(self, *, project_id: UUID, competencia) -> list[ProjectLabor]:
        competencia = normalize_competencia(competencia)
        return await self.labors.list_by_project(project_id=project_id, competencia=competencia)

    def _is_clt(self, employment_type: str | None) -> bool:
        return (employment_type or "").strip().upper() == "CLT"

    async def _labor_monthly_for_employee(self, *, employee, competencia) -> float:
        settings = await self._settings()
        if self._is_clt(employee.employment_type):
            return float(calculate_clt_cost(employee, settings, competencia.year, competencia.month))
        return float(calculate_pj_total_cost(employee))

    @staticmethod
    def _labor_allocation_factor(row: ProjectLabor) -> float:
        return float(row.allocation_percentage) / 100.0

    async def _labor_to_read(self, row: ProjectLabor) -> ProjectLaborRead:
        emp = row.employee
        if not emp:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Colaborador não carregado para o vínculo de mão de obra.",
            )
        full = await self._labor_monthly_for_employee(employee=emp, competencia=row.competencia)
        factor = self._labor_allocation_factor(row)
        pct = float(row.allocation_percentage)
        return ProjectLaborRead(
            id=row.id,
            created_at=row.created_at,
            updated_at=row.updated_at,
            project_id=row.project_id,
            competencia=normalize_competencia(row.competencia),
            employee_id=row.employee_id,
            allocation_percentage=pct,
            monthly_cost=round(full * factor, 2),
        )

    async def list_labors_read(self, *, project_id: UUID, competencia) -> list[ProjectLaborRead]:
        rows = await self.list_labors(project_id=project_id, competencia=competencia)
        out: list[ProjectLaborRead] = []
        for row in rows:
            if not row.employee:
                continue
            out.append(await self._labor_to_read(row))
        return out

    async def list_labor_details(self, *, project_id: UUID, competencia) -> list[ProjectLaborDetailItem]:
        settings = await self._settings()
        rows = await self.list_labors(project_id=project_id, competencia=competencia)
        out: list[ProjectLaborDetailItem] = []
        for row in rows:
            emp = row.employee
            if not emp:
                continue
            if self._is_clt(emp.employment_type):
                br_raw = clt_cost_breakdown(emp, settings, competencia.year, competencia.month)
            else:
                br_raw = pj_cost_breakdown(emp)
            full_cost = float(br_raw["total"])
            factor = self._labor_allocation_factor(row)
            pct = float(row.allocation_percentage)
            allocated = round(full_cost * factor, 2)
            bd_full = {k: float(v) for k, v in br_raw.items() if k != "total"}
            bd_scaled = {k: round(v * factor, 2) for k, v in bd_full.items()}
            out.append(
                ProjectLaborDetailItem(
                    labor_id=row.id,
                    employee_id=row.employee_id,
                    name=emp.full_name,
                    tipo=emp.employment_type,
                    allocation_percentage=pct,
                    full_cost=full_cost,
                    allocated_cost=allocated,
                    total_cost=allocated,
                    breakdown=LaborCostBreakdown(**bd_scaled),
                )
            )
        return out

    async def create_labor(self, *, project_id: UUID, data: dict) -> ProjectLaborRead:
        employee_id = data["employee_id"]
        competencia = normalize_competencia(data["competencia"])
        allocation_percentage = float(data.get("allocation_percentage", 100))
        if allocation_percentage < 1 or allocation_percentage > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Percentual deve ser entre 1 e 100.",
            )
        project = await ProjectRepository(self.session).get(project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado.")
        emp = await self.employees.get(employee_id)
        if not emp:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Colaborador não encontrado.")
        existing = await self.labors.get_by_project_employee_competencia(
            project_id=project_id, employee_id=employee_id, competencia=competencia
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Colaborador já vinculado a este projeto nesta competência.",
            )
        allocated_elsewhere = await self.labors.sum_allocation_percentage_for_employee_competencia(
            employee_id=employee_id, competencia=competencia
        )
        if allocated_elsewhere + allocation_percentage > 100.0001:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "A soma dos percentuais deste colaborador em todos os projetos nesta competência "
                    "não pode ultrapassar 100%."
                ),
            )
        row = ProjectLabor(
            project_id=project_id,
            competencia=competencia,
            employee_id=employee_id,
            allocation_percentage=allocation_percentage,
        )
        try:
            await self.labors.add(row)
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            kind = _project_labor_integrity_kind(e)
            if kind == "unique":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Colaborador já vinculado a este projeto nesta competência.",
                )
            if kind == "fk":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Referência inválida: projeto ou colaborador não existe no banco.",
                )
            if kind == "not_null":
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "O banco ainda tem colunas antigas em project_labors (ex.: labor_type). "
                        "Na raiz do projeto, execute: alembic upgrade head"
                    ),
                )
            orig = getattr(e, "orig", None)
            logger.exception(
                "project_labors: integridade ao criar vínculo (sqlstate=%s table=%s constraint=%s msg=%s)",
                getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None),
                getattr(orig, "table_name", None),
                getattr(orig, "constraint_name", None),
                orig,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível salvar o vínculo (projeto, colaborador ou dados inválidos).",
            ) from e
        loaded = await self.labors.get_with_employee(row.id)
        if not loaded or not loaded.employee:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro ao carregar vínculo de mão de obra.",
            )
        return await self._labor_to_read(loaded)

    async def delete_labor(self, *, labor_id: UUID) -> None:
        row = await self.labors.get(labor_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro não encontrado.")
        await self.labors.delete(row)
        await self.session.commit()

    # --- Vehicle (alocação frota → projeto) ---

    def project_vehicle_to_read(self, row: ProjectVehicle) -> ProjectVehicleRead:
        if not row.vehicle:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Veículo da frota não carregado na alocação.",
            )
        v = row.vehicle
        drv = v.driver
        return ProjectVehicleRead(
            id=row.id,
            created_at=row.created_at,
            updated_at=row.updated_at,
            project_id=row.project_id,
            competencia=normalize_competencia(row.competencia),
            vehicle_id=v.id,
            plate=v.plate,
            model=v.model,
            vehicle_type=v.vehicle_type,
            fuel_type=row.fuel_type,
            km_per_month=float(row.km_per_month),
            monthly_cost=float(row.monthly_cost),
            driver_employee_id=v.driver_employee_id,
            driver_name=drv.full_name if drv else None,
        )

    async def list_project_vehicles_read(self, *, project_id: UUID, competencia) -> list[ProjectVehicleRead]:
        competencia = normalize_competencia(competencia)
        rows = await self.vehicles.list_by_project(project_id=project_id, competencia=competencia)
        return [self.project_vehicle_to_read(r) for r in rows]

    async def create_project_vehicle(self, *, project_id: UUID, data: dict) -> ProjectVehicleRead:
        competencia = normalize_competencia(data["competencia"])
        fleet_vid = data["vehicle_id"]
        fleet_repo = FleetVehicleRepository(self.session)
        fv = await fleet_repo.get(fleet_vid)
        if not fv or not fv.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Veículo não encontrado ou inativo.",
            )
        dup = await self.vehicles.get_by_project_fleet_vehicle_competencia(
            project_id=project_id, vehicle_id=fleet_vid, competencia=competencia
        )
        if dup:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Este veículo já está alocado a este projeto nesta competência.",
            )
        settings = await self._settings()
        monthly = compute_vehicle_monthly_cost(
            settings=settings,
            vehicle_type=fv.vehicle_type,
            fuel_type=data["fuel_type"],
            km_per_month=float(data["km_per_month"]),
            fixed_monthly_cost=float(fv.monthly_cost),
        )
        row = ProjectVehicle(
            project_id=project_id,
            competencia=competencia,
            vehicle_id=fleet_vid,
            fuel_type=data["fuel_type"],
            km_per_month=data["km_per_month"],
            monthly_cost=monthly,
        )
        try:
            await self.vehicles.add(row)
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Este veículo já está alocado a este projeto nesta competência.",
            ) from e
        loaded = await self.vehicles.get_with_vehicle_and_driver(row.id)
        if not loaded:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro ao carregar alocação de veículo.",
            )
        return self.project_vehicle_to_read(loaded)

    async def update_project_vehicle(self, *, allocation_id: UUID, data: dict) -> ProjectVehicleRead:
        row = await self.vehicles.get_with_vehicle_and_driver(allocation_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro não encontrado.")
        fleet_repo = FleetVehicleRepository(self.session)
        patch = {k: v for k, v in data.items() if v is not None}
        if "vehicle_id" in patch:
            fv = await fleet_repo.get(patch["vehicle_id"])
            if not fv or not fv.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Veículo não encontrado ou inativo.",
                )
            other = await self.vehicles.get_by_project_fleet_vehicle_competencia(
                project_id=row.project_id, vehicle_id=patch["vehicle_id"], competencia=row.competencia
            )
            if other and other.id != row.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Este veículo já está alocado a este projeto nesta competência.",
                )
        for k, v in patch.items():
            setattr(row, k, v)
        fv_row = await fleet_repo.get(row.vehicle_id)
        if not fv_row:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Veículo da frota inválido.")
        settings = await self._settings()
        row.monthly_cost = compute_vehicle_monthly_cost(
            settings=settings,
            vehicle_type=fv_row.vehicle_type,
            fuel_type=row.fuel_type,
            km_per_month=float(row.km_per_month),
            fixed_monthly_cost=float(fv_row.monthly_cost),
        )
        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Este veículo já está alocado a este projeto nesta competência.",
            ) from e
        await self.session.refresh(row)
        loaded = await self.vehicles.get_with_vehicle_and_driver(row.id)
        if not loaded:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro ao carregar alocação de veículo.",
            )
        return self.project_vehicle_to_read(loaded)

    async def delete_project_vehicle(self, *, allocation_id: UUID) -> None:
        row = await self.vehicles.get(allocation_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro não encontrado.")
        await self.vehicles.delete(row)
        await self.session.commit()

    # --- Systems ---

    async def list_systems(self, *, project_id: UUID, competencia) -> list[ProjectSystemCost]:
        return await self.systems.list_by_project(project_id=project_id, competencia=competencia)

    async def create_system(self, *, project_id: UUID, data: dict) -> ProjectSystemCost:
        row = ProjectSystemCost(project_id=project_id, competencia=data["competencia"], name=data["name"], value=data["value"])
        await self.systems.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def update_system(self, *, system_id: UUID, data: dict) -> ProjectSystemCost:
        row = await self.systems.get(system_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro não encontrado.")
        self.systems.apply_updates(row, {k: v for k, v in data.items() if v is not None})
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def delete_system(self, *, system_id: UUID) -> None:
        row = await self.systems.get(system_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro não encontrado.")
        await self.systems.delete(row)
        await self.session.commit()

    # --- Operational fixed ---

    async def list_fixed(self, *, project_id: UUID, competencia) -> list[ProjectOperationalFixed]:
        return await self.fixed.list_by_project(project_id=project_id, competencia=competencia)

    async def create_fixed(self, *, project_id: UUID, data: dict) -> ProjectOperationalFixed:
        row = ProjectOperationalFixed(
            project_id=project_id, competencia=data["competencia"], name=data["name"], value=data["value"]
        )
        await self.fixed.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def update_fixed(self, *, fixed_id: UUID, data: dict) -> ProjectOperationalFixed:
        row = await self.fixed.get(fixed_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro não encontrado.")
        self.fixed.apply_updates(row, {k: v for k, v in data.items() if v is not None})
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def delete_fixed(self, *, fixed_id: UUID) -> None:
        row = await self.fixed.get(fixed_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro não encontrado.")
        await self.fixed.delete(row)
        await self.session.commit()
