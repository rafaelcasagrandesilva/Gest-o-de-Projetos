from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    assert_may_write_scenario,
    default_scenario_for_create,
    ensure_project_access,
    get_current_user,
    require_permission,
)
from app.core.permission_codes import COSTS_EDIT, COSTS_VIEW
from app.core.scenario import parse_scenario
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


_read = [Depends(require_permission(COSTS_VIEW))]

router = APIRouter()


@router.post("/project-fixed", response_model=ProjectFixedCostRead, dependencies=[Depends(require_permission(COSTS_EDIT))])
async def create_project_fixed_cost(
    payload: ProjectFixedCostCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> ProjectFixedCostRead:
    await ensure_project_access(user=actor, project_id=payload.project_id, db=db)
    data = payload.model_dump()
    sc = parse_scenario(data.get("scenario"), default=default_scenario_for_create(actor))
    await assert_may_write_scenario(
        user=actor, scenario=sc, db=db, project_id=payload.project_id
    )
    data["scenario"] = sc
    row = await CostsService(db).create_project_fixed_cost(
        actor_user_id=actor.id, data=data, actor=actor, request=request
    )
    return ProjectFixedCostRead.model_validate(row)


@router.post("/corporate", response_model=CorporateCostRead, dependencies=[Depends(require_permission(COSTS_EDIT))])
async def create_corporate_cost(
    payload: CorporateCostCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> CorporateCostRead:
    row = await CostsService(db).create_corporate_cost(
        actor_user_id=actor.id, data=payload.model_dump(), actor=actor, request=request
    )
    return CorporateCostRead.model_validate(row)


@router.post("/allocations", response_model=CostAllocationRead, dependencies=[Depends(require_permission(COSTS_EDIT))])
async def create_cost_allocation(
    payload: CostAllocationCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> CostAllocationRead:
    await ensure_project_access(user=actor, project_id=payload.project_id, db=db)
    row = await CostsService(db).create_cost_allocation(
        actor_user_id=actor.id, data=payload.model_dump(), actor=actor, request=request
    )
    return CostAllocationRead.model_validate(row)


@router.post(
    "/corporate/{corporate_cost_id}/auto-allocate",
    response_model=list[CostAllocationRead],
    dependencies=[Depends(require_permission(COSTS_EDIT))],
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
