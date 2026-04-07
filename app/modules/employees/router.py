from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permission
from app.core.permission_codes import EMPLOYEES_EDIT, EMPLOYEES_VIEW
from app.core.scenario import DEFAULT_SCENARIO, Scenario, coerce_scenario
from app.database.session import get_db
from app.models.company_staff_cost import CompanyStaffCost
from app.models.user import User
from app.repositories.company_staff_cost import CompanyStaffCostRepository
from app.schemas.employees import (
    CLTCostPreviewRequest,
    CLTCostPreviewResponse,
    CompanyStaffCostCreate,
    CompanyStaffCostRead,
    CompanyStaffCostUpdate,
    EmployeeCreate,
    EmployeeRead,
    EmployeeUpdate,
    PayrollResponse,
)
from app.services.employee_cost_service import calculate_clt_cost_fields
from app.services.employees_service import EmployeesService, default_cost_reference
from app.services.payroll_service import PayrollService
from app.services.settings_service import SettingsService
from app.utils.date_utils import get_business_days, normalize_competencia


_read = [Depends(require_permission(EMPLOYEES_VIEW))]

router = APIRouter()


@router.post("/preview-clt-cost", response_model=CLTCostPreviewResponse, dependencies=_read)
async def preview_clt_cost(
    payload: CLTCostPreviewRequest,
    db: AsyncSession = Depends(get_db),
) -> CLTCostPreviewResponse:
    settings = await SettingsService(db).get_or_create()
    add = float(payload.additional_costs or 0)
    total = calculate_clt_cost_fields(
        salary_base=payload.salary_base,
        has_periculosidade=payload.has_periculosidade,
        has_adicional_dirigida=payload.has_adicional_dirigida,
        extra_hours_50=payload.extra_hours_50,
        extra_hours_70=payload.extra_hours_70,
        extra_hours_100=payload.extra_hours_100,
        additional_costs=add,
        vr_value=float(settings.vr_value),
        clt_charges_rate=float(settings.clt_charges_rate or 0),
        year=payload.year,
        month=payload.month,
    )
    bd = get_business_days(payload.year, payload.month)
    return CLTCostPreviewResponse(
        total_cost=total,
        business_days=bd,
        reference_month=date(payload.year, payload.month, 1),
    )


def _scenario_str(sv: Scenario | str) -> str:
    return sv.value if isinstance(sv, Scenario) else str(sv)


def _staff_row_to_read(row: CompanyStaffCost) -> CompanyStaffCostRead:
    emp = getattr(row, "employee", None)
    return CompanyStaffCostRead(
        id=row.id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        employee_id=row.employee_id,
        competencia=normalize_competencia(row.competencia),
        scenario=_scenario_str(row.scenario),
        valor=float(row.valor),
        employee_full_name=emp.full_name if emp else None,
    )


@router.get("/payroll", response_model=PayrollResponse, dependencies=_read)
async def get_payroll(
    competencia: date = Query(..., description="Primeiro dia do mês"),
    scenario_param: str | None = Query(
        default=None, alias="scenario", description="PREVISTO ou REALIZADO; omitir = REALIZADO"
    ),
    project_id: UUID | None = Query(default=None, description="Filtrar alocações a um projeto (custos adm. mantidos)"),
    db: AsyncSession = Depends(get_db),
) -> PayrollResponse:
    sc = coerce_scenario(scenario_param)
    return await PayrollService(db).build_payroll(
        competencia=competencia, scenario=sc, project_id=project_id
    )


@router.get("/staff-costs", response_model=list[CompanyStaffCostRead], dependencies=_read)
async def list_staff_costs(
    competencia: date = Query(..., description="Primeiro dia do mês"),
    scenario_param: str | None = Query(default=None, alias="scenario", description="Omitir = REALIZADO"),
    db: AsyncSession = Depends(get_db),
) -> list[CompanyStaffCostRead]:
    sc = coerce_scenario(scenario_param)
    rows = await CompanyStaffCostRepository(db).list_by_competencia_scenario(
        competencia=competencia, scenario=sc
    )
    return [_staff_row_to_read(r) for r in rows]


@router.post("/staff-costs", response_model=CompanyStaffCostRead, dependencies=[Depends(require_permission(EMPLOYEES_EDIT))])
async def create_staff_cost(
    payload: CompanyStaffCostCreate,
    db: AsyncSession = Depends(get_db),
) -> CompanyStaffCostRead:
    sc = coerce_scenario(payload.scenario or DEFAULT_SCENARIO)
    comp = normalize_competencia(payload.competencia)
    row = CompanyStaffCost(
        employee_id=payload.employee_id,
        competencia=comp,
        scenario=sc,
        valor=float(payload.valor),
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe custo administrativo para este colaborador, mês e cenário.",
        ) from None
    await db.refresh(row)
    loaded = await CompanyStaffCostRepository(db).get_with_employee(row.id)
    if not loaded:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Falha ao carregar registro.")
    return _staff_row_to_read(loaded)


@router.patch(
    "/staff-costs/{cost_id}",
    response_model=CompanyStaffCostRead,
    dependencies=[Depends(require_permission(EMPLOYEES_EDIT))],
)
async def update_staff_cost(
    cost_id: UUID,
    payload: CompanyStaffCostUpdate,
    db: AsyncSession = Depends(get_db),
) -> CompanyStaffCostRead:
    repo = CompanyStaffCostRepository(db)
    row = await repo.get_with_employee(cost_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro não encontrado.")
    row.valor = float(payload.valor)
    await db.commit()
    await db.refresh(row)
    loaded = await repo.get_with_employee(cost_id)
    assert loaded is not None
    return _staff_row_to_read(loaded)


@router.delete("/staff-costs/{cost_id}", status_code=204, dependencies=[Depends(require_permission(EMPLOYEES_EDIT))])
async def delete_staff_cost(
    cost_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = CompanyStaffCostRepository(db)
    row = await repo.get(cost_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro não encontrado.")
    await repo.delete(row)
    await db.commit()


@router.get("", response_model=list[EmployeeRead], dependencies=_read)
async def list_employees(
    db: AsyncSession = Depends(get_db),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    competencia: date | None = Query(
        default=None,
        description="Primeiro dia do mês de competência para recalcular custo CLT na resposta.",
    ),
) -> list[EmployeeRead]:
    comp = competencia or default_cost_reference()
    return await EmployeesService(db).list_employees_as_read(offset=offset, limit=limit, competencia=comp)


@router.post("", response_model=EmployeeRead, dependencies=[Depends(require_permission(EMPLOYEES_EDIT))])
async def create_employee(
    payload: EmployeeCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> EmployeeRead:
    svc = EmployeesService(db)
    row = await svc.create_employee(
        actor_user_id=actor.id, data=payload.model_dump(), actor=actor, request=request
    )
    comp = payload.cost_reference_competencia or default_cost_reference()
    return await svc.employee_to_read(row, competencia=comp)


@router.patch("/{employee_id}", response_model=EmployeeRead, dependencies=[Depends(require_permission(EMPLOYEES_EDIT))])
async def update_employee(
    employee_id: UUID,
    payload: EmployeeUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> EmployeeRead:
    svc = EmployeesService(db)
    raw = payload.model_dump(exclude_unset=True)
    row = await svc.update_employee(
        actor_user_id=actor.id,
        employee_id=employee_id,
        data=raw,
        actor=actor,
        request=request,
    )
    if "cost_reference_competencia" in raw:
        comp = raw["cost_reference_competencia"] or default_cost_reference()
    else:
        comp = default_cost_reference()
    return await svc.employee_to_read(row, competencia=comp)


@router.delete("/{employee_id}", status_code=204, dependencies=[Depends(require_permission(EMPLOYEES_EDIT))])
async def delete_employee(
    employee_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> None:
    await EmployeesService(db).delete_employee(
        actor_user_id=actor.id, employee_id=employee_id, actor=actor, request=request
    )
