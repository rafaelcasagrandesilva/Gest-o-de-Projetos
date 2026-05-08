from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permission
from app.core.permission_codes import COSTS_EDIT, PAYABLES_VIEW
from app.database.session import get_db
from app.models.payable import Payable
from app.models.user import User
from app.schemas.payables import PayableCreate, PayablePay, PayableRead, PayableUpdate
from app.services.payable_service import PayableService, payable_status

router = APIRouter()

_read = [Depends(require_permission(PAYABLES_VIEW))]
_write = [Depends(require_permission(COSTS_EDIT))]


def _to_read(row) -> PayableRead:
    st = payable_status(payment_date=row.payment_date, due_date=row.due_date)
    return PayableRead.model_validate(
        {
            "id": row.id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "description": row.description,
            "supplier_name": row.supplier_name,
            "amount": float(row.amount or 0),
            "due_date": row.due_date,
            "payment_date": row.payment_date,
            "competence": row.competence,
            "chart_account_id": row.chart_account_id,
            "chart_account_code": row.chart_account.code if row.chart_account else "",
            "chart_account_name": row.chart_account.name if row.chart_account else "",
            "chart_account_type": str(row.chart_account.type) if row.chart_account else "",
            "cost_center": row.cost_center,
            "project_id": row.project_id,
            "project_name": row.project.name if row.project else None,
            "status": st,
        }
    )


@router.get("", response_model=list[PayableRead], dependencies=_read)
async def list_payables(
    competence: date | None = Query(default=None, description="Competência (YYYY-MM-01)."),
    status: str | None = Query(default=None, pattern="^(ABERTO|PAGO|ATRASADO)$"),
    chart_account_id: UUID | None = Query(default=None),
    project_id: UUID | None = Query(default=None),
    supplier: str | None = Query(default=None, max_length=255),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PayableRead]:
    _ = user
    svc = PayableService(db)
    rows = await svc.list_payables(
        competence=competence,
        status=status,
        chart_account_id=chart_account_id,
        project_id=project_id,
        supplier=supplier,
    )
    return [_to_read(r) for r in rows]


@router.post("", response_model=PayableRead, dependencies=_write)
async def create_payable(
    payload: PayableCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> PayableRead:
    _ = actor
    svc = PayableService(db)
    row = await svc.create_payable(payload.model_dump())
    await db.commit()
    await db.refresh(row, attribute_names=["chart_account", "project"])
    return _to_read(row)


@router.patch("/{payable_id}", response_model=PayableRead, dependencies=_write)
async def update_payable(
    payable_id: UUID,
    payload: PayableUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> PayableRead:
    _ = actor
    row = await db.get(Payable, payable_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Conta a pagar não encontrada.")

    data = payload.model_dump(exclude_unset=True)
    if "description" in data and data["description"] is not None:
        row.description = str(data["description"]).strip()
    if "supplier_name" in data and data["supplier_name"] is not None:
        row.supplier_name = str(data["supplier_name"]).strip()
    if "amount" in data and data["amount"] is not None:
        row.amount = data["amount"]
    if "due_date" in data and data["due_date"] is not None:
        row.due_date = data["due_date"]
    if "competence" in data and data["competence"] is not None:
        row.competence = data["competence"]
    if "chart_account_id" in data and data["chart_account_id"] is not None:
        row.chart_account_id = data["chart_account_id"]
    if "cost_center" in data:
        row.cost_center = data["cost_center"]
    if "project_id" in data:
        row.project_id = data["project_id"]

    await db.flush()
    await db.commit()
    await db.refresh(row, attribute_names=["chart_account", "project"])
    return _to_read(row)


@router.patch("/{payable_id}/pay", response_model=PayableRead, dependencies=_write)
async def mark_paid(
    payable_id: UUID,
    payload: PayablePay,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> PayableRead:
    _ = actor
    svc = PayableService(db)
    row = await svc.mark_as_paid(payable_id, payment_date=payload.payment_date)
    if row is None:
        raise HTTPException(status_code=404, detail="Conta a pagar não encontrada.")
    await db.commit()
    await db.refresh(row, attribute_names=["chart_account", "project"])
    return _to_read(row)


@router.delete("/{payable_id}", status_code=204, dependencies=_write)
async def delete_payable(
    payable_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> None:
    _ = actor
    svc = PayableService(db)
    ok = await svc.delete_payable(payable_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Conta a pagar não encontrada.")
    await db.commit()
    return None

