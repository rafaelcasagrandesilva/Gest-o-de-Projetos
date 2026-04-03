from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ROLE_ADMIN, ROLE_CONSULTA, ROLE_GESTOR, get_current_user, require_admin, require_roles
from app.database.session import get_db
from app.models.user import User
from app.schemas.employees import (
    CLTCostPreviewRequest,
    CLTCostPreviewResponse,
    EmployeeCreate,
    EmployeeRead,
    EmployeeUpdate,
)
from app.services.employee_cost_service import calculate_clt_cost_fields
from app.services.employees_service import EmployeesService, default_cost_reference
from app.services.settings_service import SettingsService
from app.utils.date_utils import get_business_days


_read = [Depends(require_roles(ROLE_ADMIN, ROLE_GESTOR, ROLE_CONSULTA))]

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


@router.post("", response_model=EmployeeRead, dependencies=[Depends(require_admin)])
async def create_employee(
    payload: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> EmployeeRead:
    svc = EmployeesService(db)
    row = await svc.create_employee(actor_user_id=actor.id, data=payload.model_dump())
    comp = payload.cost_reference_competencia or default_cost_reference()
    return await svc.employee_to_read(row, competencia=comp)


@router.patch("/{employee_id}", response_model=EmployeeRead, dependencies=[Depends(require_admin)])
async def update_employee(
    employee_id: UUID,
    payload: EmployeeUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> EmployeeRead:
    svc = EmployeesService(db)
    raw = payload.model_dump(exclude_unset=True)
    row = await svc.update_employee(
        actor_user_id=actor.id,
        employee_id=employee_id,
        data=raw,
    )
    if "cost_reference_competencia" in raw:
        comp = raw["cost_reference_competencia"] or default_cost_reference()
    else:
        comp = default_cost_reference()
    return await svc.employee_to_read(row, competencia=comp)


@router.delete("/{employee_id}", status_code=204, dependencies=[Depends(require_admin)])
async def delete_employee(
    employee_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> None:
    await EmployeesService(db).delete_employee(actor_user_id=actor.id, employee_id=employee_id)
