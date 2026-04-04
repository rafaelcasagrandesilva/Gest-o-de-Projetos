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
    ProjectLaborCopyFromPreviousResult,
    ProjectLaborCostUpdate,
    ProjectLaborDetailItem,
    ProjectLaborRead,
    ProjectVehicleRead,
)
from app.services.employee_cost_service import (
    project_labor_cost_base_source,
    project_labor_full_monthly_cost,
    project_labor_monthly_cost_breakdown,
)
from app.services.operational_cost_calc import (
    compute_project_vehicle_monthly_cost,
    fuel_cost_per_km_realized,
    vehicle_fuel_only_estimate,
)
from app.core.scenario import DEFAULT_SCENARIO, Scenario, coerce_scenario, parse_scenario
from app.services.settings_service import SettingsService
from app.utils.date_utils import normalize_competencia, previous_competencia

logger = logging.getLogger(__name__)

_PROJECT_LABOR_UNIQUE = "uq_project_labors_proj_emp_comp_scenario"


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

    async def copy_labors_from_previous_month(
        self, *, project_id: UUID, competencia, scenario: str | Scenario
    ) -> ProjectLaborCopyFromPreviousResult:
        """Copia do mês anterior apenas colaboradores ainda sem vínculo na competência (não sobrescreve)."""
        comp = normalize_competencia(competencia)
        prev = previous_competencia(comp)
        eff = coerce_scenario(scenario)
        prev_rows = await self.labors.list_by_project(project_id=project_id, competencia=prev, scenario=eff)
        cur_rows = await self.labors.list_by_project(project_id=project_id, competencia=comp, scenario=eff)
        cur_emp = {r.employee_id for r in cur_rows}
        copied = 0
        skipped_already_linked = 0
        skipped_allocation_cap = 0
        for pr in prev_rows:
            if pr.employee_id in cur_emp:
                skipped_already_linked += 1
                continue
            used = await self.labors.sum_allocation_percentage_for_employee_competencia(
                employee_id=pr.employee_id, competencia=comp, scenario=eff
            )
            pct = float(pr.allocation_percentage)
            if used + pct > 100.0001:
                skipped_allocation_cap += 1
                logger.warning(
                    "Cópia mão de obra mês anterior omitida (>100%%): employee=%s project=%s competencia=%s",
                    pr.employee_id,
                    project_id,
                    comp,
                )
                continue
            self.session.add(
                ProjectLabor(
                    project_id=project_id,
                    competencia=comp,
                    employee_id=pr.employee_id,
                    allocation_percentage=pct,
                    scenario=pr.scenario,
                    cost_salary_base=pr.cost_salary_base,
                    cost_additional_costs=pr.cost_additional_costs,
                    cost_extra_hours_50=pr.cost_extra_hours_50,
                    cost_extra_hours_70=pr.cost_extra_hours_70,
                    cost_extra_hours_100=pr.cost_extra_hours_100,
                    cost_pj_hours_per_month=pr.cost_pj_hours_per_month,
                    cost_pj_additional_cost=pr.cost_pj_additional_cost,
                    cost_total_override=pr.cost_total_override,
                )
            )
            cur_emp.add(pr.employee_id)
            copied += 1
        if copied == 0:
            return ProjectLaborCopyFromPreviousResult(
                copied=0,
                skipped_already_linked=skipped_already_linked,
                skipped_allocation_cap=skipped_allocation_cap,
            )
        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            logger.warning(
                "Cópia mão de obra mês anterior: falha de integridade project=%s competencia=%s: %s",
                project_id,
                comp,
                e,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Não foi possível copiar (conflito de dados). Atualize a tela e tente de novo.",
            ) from e
        return ProjectLaborCopyFromPreviousResult(
            copied=copied,
            skipped_already_linked=skipped_already_linked,
            skipped_allocation_cap=skipped_allocation_cap,
        )

    async def list_labors(
        self, *, project_id: UUID, competencia, scenario: str | Scenario = DEFAULT_SCENARIO
    ) -> list[ProjectLabor]:
        sc = coerce_scenario(scenario)
        competencia = normalize_competencia(competencia)
        return await self.labors.list_by_project(
            project_id=project_id, competencia=competencia, scenario=sc
        )

    def _is_clt(self, employment_type: str | None) -> bool:
        return (employment_type or "").strip().upper() == "CLT"

    @staticmethod
    def _labor_allocation_factor(row: ProjectLabor) -> float:
        return float(row.allocation_percentage) / 100.0

    def _labor_cost_snapshot_read(self, row: ProjectLabor) -> dict[str, float | None]:
        def f(x) -> float | None:
            return float(x) if x is not None else None

        return {
            "cost_salary_base": f(row.cost_salary_base),
            "cost_additional_costs": f(row.cost_additional_costs),
            "cost_extra_hours_50": f(row.cost_extra_hours_50),
            "cost_extra_hours_70": f(row.cost_extra_hours_70),
            "cost_extra_hours_100": f(row.cost_extra_hours_100),
            "cost_pj_hours_per_month": f(row.cost_pj_hours_per_month),
            "cost_pj_additional_cost": f(row.cost_pj_additional_cost),
            "cost_total_override": f(row.cost_total_override),
        }

    async def _labor_to_read(self, row: ProjectLabor) -> ProjectLaborRead:
        emp = row.employee
        if not emp:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Colaborador não carregado para o vínculo de mão de obra.",
            )
        settings = await self._settings()
        full = project_labor_full_monthly_cost(emp, settings, row.competencia, row)
        factor = self._labor_allocation_factor(row)
        pct = float(row.allocation_percentage)
        snap = self._labor_cost_snapshot_read(row)
        return ProjectLaborRead(
            id=row.id,
            created_at=row.created_at,
            updated_at=row.updated_at,
            project_id=row.project_id,
            competencia=normalize_competencia(row.competencia),
            scenario=row.scenario,
            employee_id=row.employee_id,
            allocation_percentage=pct,
            monthly_cost=round(full * factor, 2),
            cost_base_source=project_labor_cost_base_source(emp, row),
            **snap,
        )

    async def list_labors_read(
        self, *, project_id: UUID, competencia, scenario: str | Scenario = DEFAULT_SCENARIO
    ) -> list[ProjectLaborRead]:
        rows = await self.list_labors(project_id=project_id, competencia=competencia, scenario=scenario)
        out: list[ProjectLaborRead] = []
        for row in rows:
            if not row.employee:
                continue
            out.append(await self._labor_to_read(row))
        return out

    async def list_labor_details(
        self, *, project_id: UUID, competencia, scenario: str | Scenario = DEFAULT_SCENARIO
    ) -> list[ProjectLaborDetailItem]:
        settings = await self._settings()
        rows = await self.list_labors(project_id=project_id, competencia=competencia, scenario=scenario)
        out: list[ProjectLaborDetailItem] = []
        for row in rows:
            emp = row.employee
            if not emp:
                continue
            br_raw = project_labor_monthly_cost_breakdown(emp, settings, row.competencia, row)
            full_cost = float(br_raw["total"])
            factor = self._labor_allocation_factor(row)
            pct = float(row.allocation_percentage)
            allocated = round(full_cost * factor, 2)
            bd_full = {k: float(v) for k, v in br_raw.items() if k != "total"}
            bd_scaled = {k: round(v * factor, 2) for k, v in bd_full.items()}
            snap = self._labor_cost_snapshot_read(row)
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
                    uses_cost_total_override=row.cost_total_override is not None,
                    cost_base_source=project_labor_cost_base_source(emp, row),
                    **snap,
                )
            )
        return out

    async def create_labor(self, *, project_id: UUID, data: dict) -> ProjectLaborRead:
        employee_id = data["employee_id"]
        competencia = normalize_competencia(data["competencia"])
        scenario = coerce_scenario(parse_scenario(data.get("scenario"), default=DEFAULT_SCENARIO))
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
            project_id=project_id, employee_id=employee_id, competencia=competencia, scenario=scenario
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Colaborador já vinculado a este projeto nesta competência.",
            )
        allocated_elsewhere = await self.labors.sum_allocation_percentage_for_employee_competencia(
            employee_id=employee_id, competencia=competencia, scenario=scenario
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
            scenario=scenario,
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

    async def update_labor_costs(
        self, *, project_id: UUID, labor_id: UUID, payload: ProjectLaborCostUpdate
    ) -> ProjectLaborRead:
        row = await self.labors.get_with_employee(labor_id)
        if not row or row.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro não encontrado.")
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(row, k, v)
        await self.session.flush()
        await self.session.commit()
        await self.session.refresh(row)
        loaded = await self.labors.get_with_employee(labor_id)
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

    def project_vehicle_to_read(self, row: ProjectVehicle, settings) -> ProjectVehicleRead:
        if not row.vehicle:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Veículo da frota não carregado na alocação.",
            )
        v = row.vehicle
        drv = v.driver
        fixed = float(v.monthly_cost or 0)
        km_v = float(row.km_per_month) if row.km_per_month is not None else None
        fcr_v = float(row.fuel_cost_realized) if row.fuel_cost_realized is not None else None
        display_fuel = vehicle_fuel_only_estimate(
            scenario=row.scenario,
            settings=settings,
            vehicle_type=v.vehicle_type,
            fuel_type=row.fuel_type,
            km_per_month=km_v,
            fuel_cost_realized=fcr_v,
            fixed_monthly_cost=fixed,
        )
        fk = fuel_cost_per_km_realized(fcr_v, km_v)
        return ProjectVehicleRead(
            id=row.id,
            created_at=row.created_at,
            updated_at=row.updated_at,
            project_id=row.project_id,
            competencia=normalize_competencia(row.competencia),
            scenario=row.scenario,
            vehicle_id=v.id,
            plate=v.plate,
            model=v.model,
            vehicle_type=v.vehicle_type,
            fuel_type=row.fuel_type,
            km_per_month=km_v,
            fuel_cost_realized=fcr_v,
            monthly_cost=float(row.monthly_cost),
            display_fuel_cost=display_fuel,
            fuel_cost_per_km_realized=fk,
            driver_employee_id=v.driver_employee_id,
            driver_name=drv.full_name if drv else None,
        )

    async def list_project_vehicles_read(
        self, *, project_id: UUID, competencia, scenario: str | Scenario = DEFAULT_SCENARIO
    ) -> list[ProjectVehicleRead]:
        sc = coerce_scenario(scenario)
        competencia = normalize_competencia(competencia)
        rows = await self.vehicles.list_by_project(
            project_id=project_id, competencia=competencia, scenario=sc
        )
        settings = await self._settings()
        return [self.project_vehicle_to_read(r, settings) for r in rows]

    async def create_project_vehicle(self, *, project_id: UUID, data: dict) -> ProjectVehicleRead:
        competencia = normalize_competencia(data["competencia"])
        scenario = parse_scenario(data.get("scenario"), default=DEFAULT_SCENARIO)
        fleet_vid = data["vehicle_id"]
        fleet_repo = FleetVehicleRepository(self.session)
        fv = await fleet_repo.get(fleet_vid)
        if not fv or not fv.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Veículo não encontrado ou inativo.",
            )
        dup = await self.vehicles.get_by_project_fleet_vehicle_competencia(
            project_id=project_id, vehicle_id=fleet_vid, competencia=competencia, scenario=scenario
        )
        if dup:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Este veículo já está alocado a este projeto nesta competência.",
            )
        settings = await self._settings()
        sc_en = coerce_scenario(scenario)
        if sc_en == Scenario.PREVISTO:
            fuel_type = data["fuel_type"]
            km_pm = data["km_per_month"]
            fcr = None
        else:
            fuel_type = data.get("fuel_type")
            km_pm = data.get("km_per_month")
            fcr = float(data["fuel_cost_realized"])
        monthly = compute_project_vehicle_monthly_cost(
            scenario=sc_en,
            settings=settings,
            vehicle_type=fv.vehicle_type,
            fuel_type=fuel_type,
            km_per_month=float(km_pm) if km_pm is not None else None,
            fuel_cost_realized=fcr,
            fixed_monthly_cost=float(fv.monthly_cost),
        )
        row = ProjectVehicle(
            project_id=project_id,
            competencia=competencia,
            vehicle_id=fleet_vid,
            fuel_type=fuel_type,
            km_per_month=km_pm,
            fuel_cost_realized=fcr,
            monthly_cost=monthly,
            scenario=scenario,
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
        return self.project_vehicle_to_read(loaded, settings)

    async def update_project_vehicle(self, *, allocation_id: UUID, data: dict) -> ProjectVehicleRead:
        row = await self.vehicles.get_with_vehicle_and_driver(allocation_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro não encontrado.")
        fleet_repo = FleetVehicleRepository(self.session)
        patch = dict(data)
        if "vehicle_id" in patch:
            fv = await fleet_repo.get(patch["vehicle_id"])
            if not fv or not fv.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Veículo não encontrado ou inativo.",
                )
            other = await self.vehicles.get_by_project_fleet_vehicle_competencia(
                project_id=row.project_id,
                vehicle_id=patch["vehicle_id"],
                competencia=row.competencia,
                scenario=row.scenario,
            )
            if other and other.id != row.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Este veículo já está alocado a este projeto nesta competência.",
                )
        for k, v in patch.items():
            setattr(row, k, v)
        sc_en = coerce_scenario(row.scenario)
        if sc_en == Scenario.PREVISTO:
            row.fuel_cost_realized = None
        fv_row = await fleet_repo.get(row.vehicle_id)
        if not fv_row:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Veículo da frota inválido.")
        if sc_en == Scenario.PREVISTO:
            if not row.fuel_type or row.km_per_month is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No cenário PREVISTO, informe tipo de combustível e km/mês.",
                )
        elif row.fuel_cost_realized is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No cenário REALIZADO, informe o valor real de combustível (R$).",
            )
        settings = await self._settings()
        row.monthly_cost = compute_project_vehicle_monthly_cost(
            scenario=sc_en,
            settings=settings,
            vehicle_type=fv_row.vehicle_type,
            fuel_type=row.fuel_type,
            km_per_month=float(row.km_per_month) if row.km_per_month is not None else None,
            fuel_cost_realized=float(row.fuel_cost_realized) if row.fuel_cost_realized is not None else None,
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
        return self.project_vehicle_to_read(loaded, settings)

    async def delete_project_vehicle(self, *, allocation_id: UUID) -> None:
        row = await self.vehicles.get(allocation_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro não encontrado.")
        await self.vehicles.delete(row)
        await self.session.commit()

    # --- Systems ---

    async def list_systems(
        self, *, project_id: UUID, competencia, scenario: str | Scenario = DEFAULT_SCENARIO
    ) -> list[ProjectSystemCost]:
        sc = coerce_scenario(scenario)
        return await self.systems.list_by_project(
            project_id=project_id, competencia=competencia, scenario=sc
        )

    async def create_system(self, *, project_id: UUID, data: dict) -> ProjectSystemCost:
        scenario = parse_scenario(data.get("scenario"), default=DEFAULT_SCENARIO)
        row = ProjectSystemCost(
            project_id=project_id,
            competencia=data["competencia"],
            name=data["name"],
            value=data["value"],
            scenario=scenario,
        )
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

    async def list_fixed(
        self, *, project_id: UUID, competencia, scenario: str | Scenario = DEFAULT_SCENARIO
    ) -> list[ProjectOperationalFixed]:
        sc = coerce_scenario(scenario)
        return await self.fixed.list_by_project(
            project_id=project_id, competencia=competencia, scenario=sc
        )

    async def create_fixed(self, *, project_id: UUID, data: dict) -> ProjectOperationalFixed:
        scenario = parse_scenario(data.get("scenario"), default=DEFAULT_SCENARIO)
        row = ProjectOperationalFixed(
            project_id=project_id,
            competencia=data["competencia"],
            name=data["name"],
            value=data["value"],
            scenario=scenario,
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
