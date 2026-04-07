from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    assert_may_write_scenario,
    default_scenario_for_create,
    ensure_project_access,
    get_accessible_project_ids,
    get_current_user,
    require_permission,
    user_sees_all_projects,
)
from app.core.permission_codes import BILLING_VIEW, INVOICES_EDIT, INVOICES_VIEW
from app.core.scenario import coerce_scenario, parse_scenario
from app.database.session import get_db
from app.models.user import User
from app.schemas.financial import (
    InvoiceAnticipationCreate,
    InvoiceAnticipationRead,
    InvoiceCreate,
    InvoiceRead,
    RevenueCreate,
    RevenueRead,
    RevenueUpdate,
)
from app.services.financial_crud_service import FinancialCrudService


_read = [Depends(require_permission(BILLING_VIEW))]

router = APIRouter()


@router.get("/revenues", response_model=list[RevenueRead], dependencies=_read)
async def list_revenues(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    project_id: UUID | None = Query(default=None),
    scenario_param: str | None = Query(default=None, alias="scenario", description="Omitir = REALIZADO"),
) -> list[RevenueRead]:
    sc = coerce_scenario(scenario_param)
    svc = FinancialCrudService(db)
    if not user_sees_all_projects(user):
        allowed = await get_accessible_project_ids(user, db)
        if project_id is not None:
            if project_id not in allowed:
                raise HTTPException(status_code=403, detail="Sem permissão.")
            rows = await svc.list_revenues(
                offset=offset, limit=limit, project_id=project_id, scenario=sc
            )
        else:
            rows = await svc.list_revenues(
                offset=offset, limit=limit, project_ids=allowed, scenario=sc
            )
    else:
        rows = await svc.list_revenues(offset=offset, limit=limit, project_id=project_id, scenario=sc)
    return [RevenueRead.model_validate(r) for r in rows]


@router.post("/revenues", response_model=RevenueRead, dependencies=[Depends(require_permission(INVOICES_EDIT))])
async def create_revenue(
    payload: RevenueCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> RevenueRead:
    await ensure_project_access(user=actor, project_id=payload.project_id, db=db)
    data = payload.model_dump()
    sc = parse_scenario(data.get("scenario"), default=default_scenario_for_create(actor))
    await assert_may_write_scenario(
        user=actor, scenario=sc, db=db, project_id=payload.project_id
    )
    data["scenario"] = sc
    row = await FinancialCrudService(db).create_revenue(
        actor_user_id=actor.id, data=data, actor=actor, request=request
    )
    return RevenueRead.model_validate(row)


@router.patch("/revenues/{revenue_id}", response_model=RevenueRead, dependencies=[Depends(require_permission(INVOICES_EDIT))])
async def update_revenue(
    revenue_id: UUID,
    payload: RevenueUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> RevenueRead:
    svc = FinancialCrudService(db)
    row = await svc.revenues.get(revenue_id)
    if not row:
        raise HTTPException(status_code=404, detail="Receita não encontrada.")
    await ensure_project_access(user=actor, project_id=row.project_id, db=db)
    await assert_may_write_scenario(
        user=actor, scenario=row.scenario, db=db, project_id=row.project_id
    )
    row = await svc.update_revenue(
        actor_user_id=actor.id,
        revenue_id=revenue_id,
        data=payload.model_dump(exclude_unset=True),
        actor=actor,
        request=request,
    )
    return RevenueRead.model_validate(row)


@router.delete("/revenues/{revenue_id}", status_code=204, dependencies=[Depends(require_permission(INVOICES_EDIT))])
async def delete_revenue(
    revenue_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> None:
    svc = FinancialCrudService(db)
    row = await svc.revenues.get(revenue_id)
    if not row:
        raise HTTPException(status_code=404, detail="Receita não encontrada.")
    await ensure_project_access(user=actor, project_id=row.project_id, db=db)
    await assert_may_write_scenario(
        user=actor, scenario=row.scenario, db=db, project_id=row.project_id
    )
    await svc.delete_revenue(actor_user_id=actor.id, revenue_id=revenue_id, actor=actor, request=request)


@router.get("/invoices", response_model=list[InvoiceRead], dependencies=[Depends(require_permission(INVOICES_VIEW))])
async def list_invoices(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    project_id: UUID | None = Query(default=None),
) -> list[InvoiceRead]:
    svc = FinancialCrudService(db)
    if not user_sees_all_projects(user):
        allowed = await get_accessible_project_ids(user, db)
        if project_id is not None:
            if project_id not in allowed:
                raise HTTPException(status_code=403, detail="Sem permissão.")
            rows = await svc.list_invoices(offset=offset, limit=limit, project_id=project_id)
        else:
            rows = await svc.list_invoices(offset=offset, limit=limit, project_ids=allowed)
    else:
        rows = await svc.list_invoices(offset=offset, limit=limit, project_id=project_id)
    return [InvoiceRead.model_validate(r) for r in rows]


@router.post("/invoices", response_model=InvoiceRead, dependencies=[Depends(require_permission(INVOICES_EDIT))])
async def create_invoice(
    payload: InvoiceCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> InvoiceRead:
    await ensure_project_access(user=actor, project_id=payload.project_id, db=db)
    row = await FinancialCrudService(db).create_invoice(
        actor_user_id=actor.id, data=payload.model_dump(), actor=actor, request=request
    )
    return InvoiceRead.model_validate(row)


@router.post("/invoices/anticipations", response_model=InvoiceAnticipationRead, dependencies=[Depends(require_permission(INVOICES_EDIT))])
async def create_anticipation(
    payload: InvoiceAnticipationCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> InvoiceAnticipationRead:
    svc = FinancialCrudService(db)
    inv = await svc.invoices.get(payload.invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Nota fiscal não encontrada.")
    await ensure_project_access(user=actor, project_id=inv.project_id, db=db)
    row = await svc.create_anticipation(
        actor_user_id=actor.id, data=payload.model_dump(), actor=actor, request=request
    )
    return InvoiceAnticipationRead.model_validate(row)
