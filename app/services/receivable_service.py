from __future__ import annotations

from datetime import date, datetime, timezone
from calendar import monthrange
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import Project
from app.models.receivable import ReceivableInvoice, ReceivableInvoicePayment
from app.schemas.receivable import compute_nf_status


def _f(v: object) -> float:
    return float(v) if v is not None else 0.0


def month_bounds(year: int, month: int) -> tuple[date, date]:
    last = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


class ReceivableService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _totals(self, inv: ReceivableInvoice) -> tuple[float, float]:
        total_recebido = sum(_f(p.valor) for p in inv.payments)
        saldo = max(0.0, _f(inv.valor_bruto) - total_recebido)
        return total_recebido, saldo

    def _status(self, inv: ReceivableInvoice, today: date) -> str:
        total_recebido, saldo = self._totals(inv)
        return compute_nf_status(today=today, vencimento=inv.vencimento, saldo=saldo)

    def invoice_to_read(self, inv: ReceivableInvoice, today: date) -> dict:
        total_recebido, saldo = self._totals(inv)
        st = compute_nf_status(today=today, vencimento=inv.vencimento, saldo=saldo)
        pname = inv.project.name if inv.project else None
        return {
            "id": inv.id,
            "created_at": inv.created_at,
            "updated_at": inv.updated_at,
            "project_id": inv.project_id,
            "project_name": pname,
            "numero_nf": inv.numero_nf,
            "data_emissao": inv.data_emissao,
            "valor_bruto": _f(inv.valor_bruto),
            "vencimento": inv.vencimento,
            "data_prevista_pagamento": inv.data_prevista_pagamento,
            "numero_pedido": inv.numero_pedido,
            "numero_conformidade": inv.numero_conformidade,
            "observacao": inv.observacao,
            "antecipada": inv.antecipada,
            "instituicao": inv.instituicao,
            "taxa_juros_mensal": float(inv.taxa_juros_mensal) if inv.taxa_juros_mensal is not None else None,
            "total_recebido": total_recebido,
            "saldo": saldo,
            "status": st,
        }

    async def list_invoices(
        self,
        *,
        project_id: UUID | None,
        project_ids: list[UUID] | None = None,
        status_filter: str | None,
        year: int | None,
        month: int | None,
    ) -> list[ReceivableInvoice]:
        q = select(ReceivableInvoice).options(
            selectinload(ReceivableInvoice.payments),
            selectinload(ReceivableInvoice.project),
        )
        if project_id is not None:
            q = q.where(ReceivableInvoice.project_id == project_id)
        elif project_ids is not None:
            if len(project_ids) == 0:
                return []
            q = q.where(ReceivableInvoice.project_id.in_(project_ids))
        if year is not None and month is not None:
            start, end = month_bounds(year, month)
            q = q.where(
                and_(
                    ReceivableInvoice.data_emissao >= start,
                    ReceivableInvoice.data_emissao <= end,
                )
            )
        q = q.order_by(ReceivableInvoice.vencimento.desc(), ReceivableInvoice.data_emissao.desc())
        rows = (await self.db.execute(q)).scalars().unique().all()
        today = date.today()
        if status_filter is None:
            return list(rows)
        out: list[ReceivableInvoice] = []
        for inv in rows:
            if self._status(inv, today) == status_filter:
                out.append(inv)
        return out

    async def kpis(
        self,
        *,
        project_id: UUID | None,
        project_ids: list[UUID] | None = None,
        year: int | None,
        month: int | None,
    ) -> dict:
        """KPIs no escopo dos mesmos filtros de listagem (exceto status)."""
        q = select(ReceivableInvoice).options(
            selectinload(ReceivableInvoice.payments),
            selectinload(ReceivableInvoice.project),
        )
        if project_id is not None:
            q = q.where(ReceivableInvoice.project_id == project_id)
        elif project_ids is not None:
            if len(project_ids) == 0:
                return {
                    "total_a_receber": 0.0,
                    "recebido_no_mes": 0.0,
                    "em_atraso_valor": 0.0,
                    "total_nfs": 0,
                }
            q = q.where(ReceivableInvoice.project_id.in_(project_ids))
        if year is not None and month is not None:
            start, end = month_bounds(year, month)
            q = q.where(
                and_(
                    ReceivableInvoice.data_emissao >= start,
                    ReceivableInvoice.data_emissao <= end,
                )
            )
        rows = (await self.db.execute(q)).scalars().unique().all()
        today = date.today()

        total_a_receber = 0.0
        em_atraso_valor = 0.0
        for inv in rows:
            _, saldo = self._totals(inv)
            if saldo > 0:
                total_a_receber += saldo
            if self._status(inv, today) == "ATRASADA":
                em_atraso_valor += saldo

        ry = year if year is not None else today.year
        rm = month if month is not None else today.month
        rs, re_ = month_bounds(ry, rm)
        recebido_no_mes = 0.0
        for inv in rows:
            for p in inv.payments:
                if rs <= p.data_recebimento <= re_:
                    recebido_no_mes += _f(p.valor)

        return {
            "total_a_receber": round(total_a_receber, 2),
            "recebido_no_mes": round(recebido_no_mes, 2),
            "em_atraso_valor": round(em_atraso_valor, 2),
            "total_nfs": len(rows),
        }

    async def get_invoice(self, invoice_id: UUID) -> ReceivableInvoice | None:
        q = (
            select(ReceivableInvoice)
            .where(ReceivableInvoice.id == invoice_id)
            .options(selectinload(ReceivableInvoice.payments), selectinload(ReceivableInvoice.project))
        )
        return (await self.db.execute(q)).scalars().unique().one_or_none()

    async def create_invoice(self, data: dict) -> ReceivableInvoice:
        row = ReceivableInvoice(
            project_id=data["project_id"],
            numero_nf=data["numero_nf"].strip(),
            data_emissao=data["data_emissao"],
            valor_bruto=data["valor_bruto"],
            vencimento=data["vencimento"],
            data_prevista_pagamento=data.get("data_prevista_pagamento"),
            numero_pedido=data.get("numero_pedido"),
            numero_conformidade=data.get("numero_conformidade"),
            observacao=data.get("observacao"),
            antecipada=bool(data.get("antecipada", False)),
            instituicao=data.get("instituicao"),
            taxa_juros_mensal=data.get("taxa_juros_mensal"),
        )
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        await self.db.refresh(row, attribute_names=["project"])
        return row

    async def update_invoice(self, invoice_id: UUID, data: dict) -> ReceivableInvoice | None:
        inv = await self.get_invoice(invoice_id)
        if inv is None:
            return None
        for k, v in data.items():
            if k == "numero_nf" and v is not None:
                setattr(inv, k, str(v).strip())
            else:
                setattr(inv, k, v)
        inv.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(inv, attribute_names=["payments", "project"])
        return inv

    async def delete_invoice(self, invoice_id: UUID) -> bool:
        inv = await self.get_invoice(invoice_id)
        if inv is None:
            return False
        await self.db.delete(inv)
        await self.db.flush()
        return True

    async def list_payments(self, invoice_id: UUID) -> list[ReceivableInvoicePayment]:
        inv = await self.get_invoice(invoice_id)
        if inv is None:
            return []
        return sorted(inv.payments, key=lambda p: p.data_recebimento)

    async def add_payment(self, invoice_id: UUID, data: dict) -> ReceivableInvoicePayment | None:
        inv = await self.get_invoice(invoice_id)
        if inv is None:
            return None
        pay = ReceivableInvoicePayment(
            invoice_id=invoice_id,
            data_recebimento=data["data_recebimento"],
            valor=data["valor"],
        )
        self.db.add(pay)
        inv.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(pay)
        return pay

    async def delete_payment(self, payment_id: UUID) -> bool:
        pay = await self.db.get(ReceivableInvoicePayment, payment_id)
        if pay is None:
            return False
        inv = await self.get_invoice(pay.invoice_id)
        await self.db.delete(pay)
        if inv:
            inv.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return True
