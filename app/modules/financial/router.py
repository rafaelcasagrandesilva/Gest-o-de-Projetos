from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    ROLE_ADMIN,
    ROLE_CONSULTA,
    ROLE_GESTOR,
    _user_role_names,
    ensure_project_access,
    get_current_user,
    get_user_projects,
    require_roles,
)
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


_read = [Depends(require_roles(ROLE_ADMIN, ROLE_GESTOR, ROLE_CONSULTA))]

router = APIRouter()


@router.get("/revenues", response_model=list[RevenueRead], dependencies=_read)
async def list_revenues(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    project_id: UUID | None = Query(default=None),
) -> list[RevenueRead]:
    names = _user_role_names(user)
    svc = FinancialCrudService(db)
    if ROLE_GESTOR in names and ROLE_ADMIN not in names:
        allowed = await get_user_projects(user.id, db)
        if project_id is not None:
            if project_id not in allowed:
                raise HTTPException(status_code=403, detail="Sem permissão.")
            rows = await svc.list_revenues(offset=offset, limit=limit, project_id=project_id)
        else:
            rows = await svc.list_revenues(offset=offset, limit=limit, project_ids=allowed)
    else:
        rows = await svc.list_revenues(offset=offset, limit=limit, project_id=project_id)
    return [RevenueRead.model_validate(r) for r in rows]


@router.post("/revenues", response_model=RevenueRead, dependencies=_read)
async def create_revenue(
    payload: RevenueCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> RevenueRead:
    await ensure_project_access(user=actor, project_id=payload.project_id, db=db)
    row = await FinancialCrudService(db).create_revenue(actor_user_id=actor.id, data=payload.model_dump())
    return RevenueRead.model_validate(row)


@router.patch("/revenues/{revenue_id}", response_model=RevenueRead, dependencies=_read)
async def update_revenue(
    revenue_id: UUID,
    payload: RevenueUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> RevenueRead:
    svc = FinancialCrudService(db)
    row = await svc.revenues.get(revenue_id)
    if not row:
        raise HTTPException(status_code=404, detail="Receita não encontrada.")
    await ensure_project_access(user=actor, project_id=row.project_id, db=db)
    row = await svc.update_revenue(
        actor_user_id=actor.id, revenue_id=revenue_id, data=payload.model_dump(exclude_unset=True)
    )
    return RevenueRead.model_validate(row)


@router.delete("/revenues/{revenue_id}", status_code=204, dependencies=_read)
async def delete_revenue(
    revenue_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> None:
    svc = FinancialCrudService(db)
    row = await svc.revenues.get(revenue_id)
    if not row:
        raise HTTPException(status_code=404, detail="Receita não encontrada.")
    await ensure_project_access(user=actor, project_id=row.project_id, db=db)
    await svc.delete_revenue(actor_user_id=actor.id, revenue_id=revenue_id)


@router.get("/invoices", response_model=list[InvoiceRead], dependencies=_read)
async def list_invoices(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    project_id: UUID | None = Query(default=None),
) -> list[InvoiceRead]:
    names = _user_role_names(user)
    svc = FinancialCrudService(db)
    if ROLE_GESTOR in names and ROLE_ADMIN not in names:
        allowed = await get_user_projects(user.id, db)
        if project_id is not None:
            if project_id not in allowed:
                raise HTTPException(status_code=403, detail="Sem permissão.")
            rows = await svc.list_invoices(offset=offset, limit=limit, project_id=project_id)
        else:
            rows = await svc.list_invoices(offset=offset, limit=limit, project_ids=allowed)
    else:
        rows = await svc.list_invoices(offset=offset, limit=limit, project_id=project_id)
    return [InvoiceRead.model_validate(r) for r in rows]


@router.post("/invoices", response_model=InvoiceRead, dependencies=_read)
async def create_invoice(
    payload: InvoiceCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> InvoiceRead:
    await ensure_project_access(user=actor, project_id=payload.project_id, db=db)
    row = await FinancialCrudService(db).create_invoice(actor_user_id=actor.id, data=payload.model_dump())
    return InvoiceRead.model_validate(row)


@router.post("/invoices/anticipations", response_model=InvoiceAnticipationRead, dependencies=_read)
async def create_anticipation(
    payload: InvoiceAnticipationCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> InvoiceAnticipationRead:
    svc = FinancialCrudService(db)
    inv = await svc.invoices.get(payload.invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Nota fiscal não encontrada.")
    await ensure_project_access(user=actor, project_id=inv.project_id, db=db)
    row = await svc.create_anticipation(actor_user_id=actor.id, data=payload.model_dump())
    return InvoiceAnticipationRead.model_validate(row)
