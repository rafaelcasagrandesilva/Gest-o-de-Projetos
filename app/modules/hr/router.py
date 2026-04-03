from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    ROLE_ADMIN,
    ROLE_CONSULTA,
    ROLE_GESTOR,
    ensure_project_access,
    get_current_user,
    require_admin,
    require_roles,
)
from app.database.session import get_db
from app.models.user import User
from app.schemas.employees import (
    EmployeeAllocationCreate,
    EmployeeAllocationRead,
    EmployeeCreate,
    EmployeeRead,
    EmployeeUpdate,
)
from app.services.employees_service import EmployeesService, default_cost_reference


_read = [Depends(require_roles(ROLE_ADMIN, ROLE_GESTOR, ROLE_CONSULTA))]

router = APIRouter()


@router.get("/employees", response_model=list[EmployeeRead], dependencies=_read)
async def list_employees(
    db: AsyncSession = Depends(get_db),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    competencia: date | None = Query(
        default=None,
        description="Primeiro dia do mês de competência para custo CLT na resposta.",
    ),
) -> list[EmployeeRead]:
    comp = competencia or default_cost_reference()
    return await EmployeesService(db).list_employees_as_read(offset=offset, limit=limit, competencia=comp)


@router.post("/employees", response_model=EmployeeRead, dependencies=[Depends(require_admin)])
async def create_employee(
    payload: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> EmployeeRead:
    svc = EmployeesService(db)
    row = await svc.create_employee(actor_user_id=actor.id, data=payload.model_dump())
    comp = payload.cost_reference_competencia or default_cost_reference()
    return await svc.employee_to_read(row, competencia=comp)


@router.patch("/employees/{employee_id}", response_model=EmployeeRead, dependencies=[Depends(require_admin)])
async def update_employee(
    employee_id,
    payload: EmployeeUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> EmployeeRead:
    svc = EmployeesService(db)
    raw = payload.model_dump(exclude_unset=True)
    row = await svc.update_employee(
        actor_user_id=actor.id, employee_id=employee_id, data=raw,
    )
    if "cost_reference_competencia" in raw:
        comp = raw["cost_reference_competencia"] or default_cost_reference()
    else:
        comp = default_cost_reference()
    return await svc.employee_to_read(row, competencia=comp)


@router.delete("/employees/{employee_id}", status_code=204, dependencies=[Depends(require_admin)])
async def delete_employee(
    employee_id,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> None:
    await EmployeesService(db).delete_employee(actor_user_id=actor.id, employee_id=employee_id)


@router.post("/allocations", response_model=EmployeeAllocationRead, dependencies=_read)
async def create_allocation(
    payload: EmployeeAllocationCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> EmployeeAllocationRead:
    await ensure_project_access(user=actor, project_id=payload.project_id, db=db)
    row = await EmployeesService(db).create_allocation(actor_user_id=actor.id, data=payload.model_dump())
    return EmployeeAllocationRead.model_validate(row)
