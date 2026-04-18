from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.receivable import DUE_DAYS_CHOICES, ReceivableInvoice
from app.schemas.receivable import (
    CENT_TOL,
    compute_due_date,
    compute_implied_monthly_rate_percent,
    compute_interest_amount,
    derive_invoice_status,
)


def _f(v: object) -> float:
    return float(v) if v is not None else 0.0


def month_bounds(year: int, month: int) -> tuple[date, date]:
    last = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


class ReceivableService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def append_log(self, inv: ReceivableInvoice, line: str) -> None:
        prev = (inv.activity_log or "").strip()
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        new_line = f"[{ts}] {line}"
        inv.activity_log = (prev + "\n" + new_line).strip() if prev else new_line

    def _sync_due_date(self, inv: ReceivableInvoice) -> None:
        if inv.due_days in DUE_DAYS_CHOICES:
            inv.due_date = compute_due_date(inv.issue_date, inv.due_days)

    def _sync_effective_status(self, inv: ReceivableInvoice) -> None:
        """Persiste status derivado, exceto CANCELADA explícita."""
        if inv.invoice_status == "CANCELADA":
            return
        inv.invoice_status = derive_invoice_status(
            stored_status=inv.invoice_status,
            is_anticipated=inv.is_anticipated,
            received_amount=_f(inv.received_amount),
            net_amount=_f(inv.net_amount),
        )

    def _validate_full_receipt(self, inv: ReceivableInvoice) -> None:
        ra = _f(inv.received_amount)
        if ra <= CENT_TOL:
            inv.received_date = None
            return
        net = _f(inv.net_amount)
        if abs(ra - net) > CENT_TOL and ra > CENT_TOL:
            raise ValueError("Recebimento deve ser integral: received_amount deve ser 0 ou igual ao valor líquido.")

    def invoice_to_read(self, inv: ReceivableInvoice, *, api_prefix: str = "/api/v1") -> dict:
        self._sync_effective_status(inv)
        gross = _f(inv.gross_amount)
        net = _f(inv.net_amount)
        recv = _f(inv.received_amount)
        interest = compute_interest_amount(
            is_anticipated=inv.is_anticipated, net_amount=net, received_amount=recv
        )
        eff = derive_invoice_status(
            stored_status=inv.invoice_status,
            is_anticipated=inv.is_anticipated,
            received_amount=recv,
            net_amount=net,
        )
        has_pdf = bool((inv.pdf_path or "").strip())
        pdf_url = f"{api_prefix}/invoices/{inv.id}/pdf/" if has_pdf else None
        pname = inv.project.name if inv.project else None
        return {
            "id": inv.id,
            "created_at": inv.created_at,
            "updated_at": inv.updated_at,
            "project_id": inv.project_id,
            "project_name": pname,
            "number": inv.nf_number,
            "issue_date": inv.issue_date,
            "due_days": inv.due_days,
            "due_date": inv.due_date,
            "gross_amount": gross,
            "net_amount": net,
            "client_name": inv.client_name,
            "notes": inv.notes,
            "is_anticipated": inv.is_anticipated,
            "institution": inv.institution,
            "received_amount": recv,
            "received_date": inv.received_date,
            "interest_amount": interest,
            "implied_monthly_rate_percent": compute_implied_monthly_rate_percent(
                gross_amount=gross, net_amount=net
            ),
            "status": eff,
            "has_pdf": has_pdf,
            "pdf_url": pdf_url,
            "activity_log": inv.activity_log,
        }

    async def list_invoices(
        self,
        *,
        project_id: UUID | None,
        project_ids: list[UUID] | None = None,
        status: str | None = None,
        client_busca: str | None = None,
        year: int | None,
        month: int | None,
        period_field: str = "issue",
    ) -> list[ReceivableInvoice]:
        q = select(ReceivableInvoice).options(selectinload(ReceivableInvoice.project))
        if project_id is not None:
            q = q.where(ReceivableInvoice.project_id == project_id)
        elif project_ids is not None:
            if len(project_ids) == 0:
                return []
            q = q.where(ReceivableInvoice.project_id.in_(project_ids))
        if year is not None and month is not None:
            start, end = month_bounds(year, month)
            col = ReceivableInvoice.issue_date if period_field == "issue" else ReceivableInvoice.due_date
            q = q.where(and_(col >= start, col <= end))
        if client_busca and client_busca.strip():
            pat = f"%{client_busca.strip()}%"
            q = q.where(ReceivableInvoice.client_name.ilike(pat))
        q = q.order_by(ReceivableInvoice.due_date.desc(), ReceivableInvoice.issue_date.desc())
        rows = (await self.db.execute(q)).scalars().unique().all()
        if status is None:
            return list(rows)
        out: list[ReceivableInvoice] = []
        for inv in rows:
            eff = derive_invoice_status(
                stored_status=inv.invoice_status,
                is_anticipated=inv.is_anticipated,
                received_amount=_f(inv.received_amount),
                net_amount=_f(inv.net_amount),
            )
            if eff == status:
                out.append(inv)
        return out

    async def kpis(
        self,
        *,
        project_id: UUID | None,
        project_ids: list[UUID] | None = None,
        year: int | None,
        month: int | None,
        period_field: str = "issue",
    ) -> dict:
        q = select(ReceivableInvoice).options(selectinload(ReceivableInvoice.project))
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
            col = ReceivableInvoice.issue_date if period_field == "issue" else ReceivableInvoice.due_date
            q = q.where(and_(col >= start, col <= end))
        rows = (await self.db.execute(q)).scalars().unique().all()
        today = date.today()

        total_a_receber = 0.0
        em_atraso_valor = 0.0
        for inv in rows:
            if inv.invoice_status == "CANCELADA":
                continue
            net = _f(inv.net_amount)
            recv = _f(inv.received_amount)
            saldo = max(0.0, net - recv)
            if saldo > CENT_TOL:
                total_a_receber += saldo
            if inv.due_date < today and recv < net - CENT_TOL and inv.invoice_status != "CANCELADA":
                em_atraso_valor += saldo

        ry = year if year is not None else today.year
        rm = month if month is not None else today.month
        rs, re_ = month_bounds(ry, rm)
        recebido_no_mes = 0.0
        for inv in rows:
            if inv.received_date and rs <= inv.received_date <= re_:
                recebido_no_mes += _f(inv.received_amount)

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
            .options(selectinload(ReceivableInvoice.project))
        )
        return (await self.db.execute(q)).scalars().unique().one_or_none()

    async def create_invoice(self, data: dict, *, log_user: str | None = None) -> ReceivableInvoice:
        net = data.get("net_amount")
        if net is None:
            net = data["gross_amount"]
        due_days = int(data["due_days"])
        issue = data["issue_date"]
        due_date = compute_due_date(issue, due_days)
        row = ReceivableInvoice(
            project_id=data["project_id"],
            nf_number=data["number"].strip(),
            issue_date=issue,
            due_days=due_days,
            due_date=due_date,
            gross_amount=data["gross_amount"],
            net_amount=net,
            client_name=data.get("client_name"),
            notes=data.get("notes"),
            is_anticipated=False,
            received_amount=0,
            invoice_status="EMITIDA",
        )
        self._sync_effective_status(row)
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        await self.db.refresh(row, attribute_names=["project"])
        who = log_user or "sistema"
        self.append_log(row, f"NF criada por {who}.")
        await self.db.flush()
        return row

    async def update_invoice(self, invoice_id: UUID, data: dict, *, log_user: str | None = None) -> ReceivableInvoice | None:
        inv = await self.get_invoice(invoice_id)
        if inv is None:
            return None
        if inv.invoice_status == "CANCELADA":
            if "notes" in data:
                inv.notes = data["notes"]
            inv.updated_at = datetime.now(timezone.utc)
            await self.db.flush()
            await self.db.refresh(inv, attribute_names=["project"])
            return inv

        if "number" in data and data["number"] is not None:
            inv.nf_number = str(data["number"]).strip()
        if "issue_date" in data and data["issue_date"] is not None:
            inv.issue_date = data["issue_date"]
        if "due_days" in data and data["due_days"] is not None:
            inv.due_days = int(data["due_days"])
        if "gross_amount" in data and data["gross_amount"] is not None:
            inv.gross_amount = data["gross_amount"]
        if "net_amount" in data and data["net_amount"] is not None:
            inv.net_amount = data["net_amount"]
        if "client_name" in data:
            inv.client_name = data["client_name"]
        if "notes" in data:
            inv.notes = data["notes"]
        if "is_anticipated" in data and data["is_anticipated"] is not None:
            inv.is_anticipated = bool(data["is_anticipated"])
        if "institution" in data:
            inv.institution = data["institution"]
        if "received_amount" in data and data["received_amount"] is not None:
            inv.received_amount = data["received_amount"]
        if "received_date" in data:
            inv.received_date = data["received_date"]
        if "status" in data and data["status"] is not None:
            inv.invoice_status = data["status"]

        self._sync_due_date(inv)
        self._validate_full_receipt(inv)
        self._sync_effective_status(inv)
        inv.updated_at = datetime.now(timezone.utc)
        who = log_user or "sistema"
        self.append_log(inv, f"NF atualizada por {who}.")
        await self.db.flush()
        await self.db.refresh(inv, attribute_names=["project"])
        return inv

    async def delete_invoice(self, invoice_id: UUID) -> bool:
        inv = await self.get_invoice(invoice_id)
        if inv is None:
            return False
        await self.db.delete(inv)
        await self.db.flush()
        return True

    async def set_pdf_path(
        self, invoice_id: UUID, relative_path: str, *, log_user: str | None = None
    ) -> ReceivableInvoice | None:
        inv = await self.get_invoice(invoice_id)
        if inv is None:
            return None
        inv.pdf_path = relative_path
        inv.updated_at = datetime.now(timezone.utc)
        who = log_user or "sistema"
        self.append_log(inv, f"PDF da NF anexado ou atualizado por {who}.")
        await self.db.flush()
        return inv

    async def clear_pdf(self, invoice_id: UUID, *, log_user: str | None = None) -> ReceivableInvoice | None:
        inv = await self.get_invoice(invoice_id)
        if inv is None:
            return None
        inv.pdf_path = None
        inv.updated_at = datetime.now(timezone.utc)
        who = log_user or "sistema"
        self.append_log(inv, f"PDF da NF removido por {who}.")
        await self.db.flush()
        return inv
