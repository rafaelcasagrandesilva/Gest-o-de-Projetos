from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    ROLE_CONSULTA,
    ROLE_ADMIN,
    ROLE_GESTOR,
    ensure_project_access,
    get_current_user,
    require_admin,
    require_roles,
)
from app.database.session import get_db
from app.models.user import User
from app.schemas.costs import (
    CorporateCostCreate,
    CorporateCostRead,
    CostAllocationCreate,
    CostAllocationRead,
    ProjectFixedCostCreate,
    ProjectFixedCostRead,
)
from app.services.allocation_service import AllocationService
from app.services.costs_service import CostsService


_read = [Depends(require_roles(ROLE_ADMIN, ROLE_GESTOR, ROLE_CONSULTA))]

router = APIRouter()


@router.post("/project-fixed", response_model=ProjectFixedCostRead, dependencies=_read)
async def create_project_fixed_cost(
    payload: ProjectFixedCostCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> ProjectFixedCostRead:
    await ensure_project_access(user=actor, project_id=payload.project_id, db=db)
    row = await CostsService(db).create_project_fixed_cost(actor_user_id=actor.id, data=payload.model_dump())
    return ProjectFixedCostRead.model_validate(row)


@router.post("/corporate", response_model=CorporateCostRead, dependencies=[Depends(require_admin)])
async def create_corporate_cost(
    payload: CorporateCostCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> CorporateCostRead:
    row = await CostsService(db).create_corporate_cost(actor_user_id=actor.id, data=payload.model_dump())
    return CorporateCostRead.model_validate(row)


@router.post("/allocations", response_model=CostAllocationRead, dependencies=_read)
async def create_cost_allocation(
    payload: CostAllocationCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> CostAllocationRead:
    await ensure_project_access(user=actor, project_id=payload.project_id, db=db)
    row = await CostsService(db).create_cost_allocation(actor_user_id=actor.id, data=payload.model_dump())
    return CostAllocationRead.model_validate(row)


@router.post(
    "/corporate/{corporate_cost_id}/auto-allocate",
    response_model=list[CostAllocationRead],
    dependencies=[Depends(require_admin)],
)
async def auto_allocate_corporate_cost(
    corporate_cost_id,
    competencia: date,
    db: AsyncSession = Depends(get_db),
) -> list[CostAllocationRead]:
    rows = await AllocationService(db).calcular_rateio_de_custos(
        corporate_cost_id=corporate_cost_id, competencia=competencia, strategy="by_revenue"
    )
    return [CostAllocationRead.model_validate(r) for r in rows]
