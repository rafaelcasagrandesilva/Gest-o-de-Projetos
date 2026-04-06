from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    ensure_project_access,
    get_accessible_project_ids,
    get_current_user,
    require_permission,
    user_sees_all_projects,
)
from app.core.permission_codes import INVOICES_EDIT, INVOICES_VIEW
from app.database.session import get_db
from app.models.receivable import ReceivableInvoicePayment
from app.models.user import User
from app.schemas.receivable import (
    ReceivableInvoiceCreate,
    ReceivableInvoicePaymentRead,
    ReceivableInvoiceRead,
    ReceivableInvoiceUpdate,
    ReceivableInvoicePaymentCreate,
    ReceivableKpisRead,
)
from app.services.receivable_service import ReceivableService


_read_view = [Depends(require_permission(INVOICES_VIEW))]

invoices_router = APIRouter()
payments_router = APIRouter()


@invoices_router.get("", response_model=list[ReceivableInvoiceRead], dependencies=_read_view)
async def list_invoices(
    project_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(PAGA|PENDENTE|ATRASADA)$"),
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ReceivableInvoiceRead]:
    if (year is None) != (month is None):
        raise HTTPException(status_code=400, detail="Informe ano e mês juntos para o período, ou deixe ambos vazios.")
    svc = ReceivableService(db)
    if not user_sees_all_projects(user):
        allowed = await get_accessible_project_ids(user, db)
        if project_id is not None:
            if project_id not in allowed:
                raise HTTPException(status_code=403, detail="Sem permissão.")
            rows = await svc.list_invoices(
                project_id=project_id,
                project_ids=None,
                status_filter=status,
                year=year,
                month=month,
            )
        else:
            rows = await svc.list_invoices(
                project_id=None,
                project_ids=allowed,
                status_filter=status,
                year=year,
                month=month,
            )
    else:
        rows = await svc.list_invoices(
            project_id=project_id,
            project_ids=None,
            status_filter=status,
            year=year,
            month=month,
        )
    today = date.today()
    return [ReceivableInvoiceRead.model_validate(svc.invoice_to_read(r, today)) for r in rows]


@invoices_router.get("/kpis", response_model=ReceivableKpisRead, dependencies=_read_view)
async def get_kpis(
    project_id: UUID | None = Query(default=None),
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReceivableKpisRead:
    if (year is None) != (month is None):
        raise HTTPException(status_code=400, detail="Informe ano e mês juntos para o período, ou deixe ambos vazios.")
    svc = ReceivableService(db)
    if not user_sees_all_projects(user):
        allowed = await get_accessible_project_ids(user, db)
        if project_id is not None:
            if project_id not in allowed:
                raise HTTPException(status_code=403, detail="Sem permissão.")
            data = await svc.kpis(project_id=project_id, project_ids=None, year=year, month=month)
        else:
            data = await svc.kpis(project_id=None, project_ids=allowed, year=year, month=month)
    else:
        data = await svc.kpis(project_id=project_id, project_ids=None, year=year, month=month)
    return ReceivableKpisRead.model_validate(data)


@invoices_router.post("", response_model=ReceivableInvoiceRead, dependencies=[Depends(require_permission(INVOICES_EDIT))])
async def create_invoice(
    payload: ReceivableInvoiceCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> ReceivableInvoiceRead:
    await ensure_project_access(user=actor, project_id=payload.project_id, db=db)
    svc = ReceivableService(db)
    row = await svc.create_invoice(payload.model_dump())
    await db.commit()
    loaded = await svc.get_invoice(row.id)
    if loaded is None:
        raise HTTPException(status_code=500, detail="Falha ao carregar NF")
    today = date.today()
    return ReceivableInvoiceRead.model_validate(svc.invoice_to_read(loaded, today))


@invoices_router.patch("/{invoice_id}", response_model=ReceivableInvoiceRead, dependencies=[Depends(require_permission(INVOICES_EDIT))])
async def update_invoice(
    invoice_id: UUID,
    payload: ReceivableInvoiceUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> ReceivableInvoiceRead:
    svc = ReceivableService(db)
    inv = await svc.get_invoice(invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    await ensure_project_access(user=actor, project_id=inv.project_id, db=db)
    data = payload.model_dump(exclude_unset=True)
    row = await svc.update_invoice(invoice_id, data)
    if row is None:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    await db.commit()
    loaded = await svc.get_invoice(invoice_id)
    if loaded is None:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    today = date.today()
    return ReceivableInvoiceRead.model_validate(svc.invoice_to_read(loaded, today))


@invoices_router.delete("/{invoice_id}", status_code=204, dependencies=[Depends(require_permission(INVOICES_EDIT))])
async def delete_invoice(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> None:
    svc = ReceivableService(db)
    inv = await svc.get_invoice(invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    await ensure_project_access(user=actor, project_id=inv.project_id, db=db)
    ok = await svc.delete_invoice(invoice_id)
    if not ok:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    await db.commit()


@invoices_router.get("/{invoice_id}/payments", response_model=list[ReceivableInvoicePaymentRead], dependencies=_read_view)
async def list_payments(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ReceivableInvoicePaymentRead]:
    svc = ReceivableService(db)
    inv = await svc.get_invoice(invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    await ensure_project_access(user=user, project_id=inv.project_id, db=db)
    pays = await svc.list_payments(invoice_id)
    return [ReceivableInvoicePaymentRead.model_validate(p) for p in pays]


@invoices_router.post("/{invoice_id}/payments", response_model=ReceivableInvoicePaymentRead, dependencies=[Depends(require_permission(INVOICES_EDIT))])
async def add_payment(
    invoice_id: UUID,
    payload: ReceivableInvoicePaymentCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> ReceivableInvoicePaymentRead:
    svc = ReceivableService(db)
    inv = await svc.get_invoice(invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    await ensure_project_access(user=actor, project_id=inv.project_id, db=db)
    pay = await svc.add_payment(invoice_id, payload.model_dump())
    if pay is None:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    await db.commit()
    await db.refresh(pay)
    return ReceivableInvoicePaymentRead.model_validate(pay)


@payments_router.delete("/{payment_id}", status_code=204, dependencies=[Depends(require_permission(INVOICES_EDIT))])
async def delete_payment(
    payment_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> None:
    pay = await db.get(ReceivableInvoicePayment, payment_id)
    if pay is None:
        raise HTTPException(status_code=404, detail="Recebimento não encontrado")
    svc = ReceivableService(db)
    inv = await svc.get_invoice(pay.invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    await ensure_project_access(user=actor, project_id=inv.project_id, db=db)
    ok = await svc.delete_payment(payment_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Recebimento não encontrado")
    await db.commit()
