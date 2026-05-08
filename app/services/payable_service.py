from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from calendar import monthrange
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.payable import Payable
from app.utils.date_utils import normalize_competencia


def month_bounds(year: int, month: int) -> tuple[date, date]:
    last = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def payable_status(*, payment_date: date | None, due_date: date, today: date | None = None) -> str:
    t = today or date.today()
    if payment_date is not None:
        return "PAGO"
    if t > due_date:
        return "ATRASADO"
    return "ABERTO"


class PayableService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_payable(self, data: dict) -> Payable:
        comp = normalize_competencia(data["competence"])
        row = Payable(
            description=str(data["description"]).strip(),
            supplier_name=str(data["supplier_name"]).strip(),
            amount=data["amount"],
            due_date=data["due_date"],
            payment_date=None,
            competence=comp,
            chart_account_id=data["chart_account_id"],
            cost_center=data.get("cost_center"),
            project_id=data.get("project_id"),
        )
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row, attribute_names=["chart_account", "project"])
        return row

    async def list_payables(
        self,
        *,
        competence: date | None,
        status: str | None,
        chart_account_id: UUID | None,
        project_id: UUID | None,
        supplier: str | None,
    ) -> list[Payable]:
        q = select(Payable).options(selectinload(Payable.chart_account), selectinload(Payable.project))
        if competence is not None:
            comp = normalize_competencia(competence)
            start, end = month_bounds(comp.year, comp.month)
            q = q.where(and_(Payable.competence >= start, Payable.competence <= end))
        if chart_account_id is not None:
            q = q.where(Payable.chart_account_id == chart_account_id)
        if project_id is not None:
            q = q.where(Payable.project_id == project_id)
        if supplier and supplier.strip():
            pat = f"%{supplier.strip()}%"
            q = q.where(Payable.supplier_name.ilike(pat))
        q = q.order_by(Payable.due_date.desc(), Payable.created_at.desc())

        rows = (await self.db.execute(q)).scalars().unique().all()
        if status is None:
            return list(rows)

        today = date.today()
        out: list[Payable] = []
        for r in rows:
            if payable_status(payment_date=r.payment_date, due_date=r.due_date, today=today) == status:
                out.append(r)
        return out

    async def mark_as_paid(self, payable_id: UUID, *, payment_date: date) -> Payable | None:
        row = await self.db.get(Payable, payable_id)
        if row is None:
            return None
        row.payment_date = payment_date
        row.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(row, attribute_names=["chart_account", "project"])
        return row

    async def delete_payable(self, payable_id: UUID) -> bool:
        row = await self.db.get(Payable, payable_id)
        if row is None:
            return False
        await self.db.delete(row)
        await self.db.flush()
        return True

