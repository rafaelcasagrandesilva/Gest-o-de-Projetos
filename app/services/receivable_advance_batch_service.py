from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import MissingGreenlet

from app.models.project import Project
from app.models.receivable import ReceivableInvoice, ReceivableInvoiceAnticipation
from app.models.receivable_advance_batch import (
    ReceivableAdvanceBatch,
    ReceivableAdvanceBatchItem,
    ReceivableAdvanceBatchStatus,
)
from app.models.payable_snapshot import PayableSnapshotType
from app.schemas.receivable import CENT_TOL, derive_invoice_status
from app.services.payable_snapshot_service import PayableSnapshotService
from app.services.receivable_service import ReceivableService, get_affected_months
from app.utils.date_utils import normalize_competencia


def _money(v: float | Decimal) -> Decimal:
    return Decimal(str(round(float(v), 2)))


def _next_batch_number(existing: list[str], *, year: int) -> str:
    prefix = f"BT-{year}-"
    max_seq = 0
    for num in existing:
        if not num.startswith(prefix):
            continue
        tail = num[len(prefix) :]
        try:
            max_seq = max(max_seq, int(tail))
        except ValueError:
            continue
    return f"{prefix}{max_seq + 1:04d}"


def _op_display_code(*, batch_number: str, operation_code: str | None, batch_id: UUID | None = None) -> str:
    """Código exibível da operação (preferir operation_code; fallback determinístico)."""
    code = (operation_code or "").strip()
    if code:
        return code
    if batch_number:
        return batch_number
    if batch_id:
        return f"ANTECIPACAO-{str(batch_id)[:8]}"
    return "ANTECIPACAO"


class ReceivableAdvanceBatchService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _invoice_in_active_batch(self, invoice_id: UUID) -> ReceivableAdvanceBatch | None:
        stmt = (
            select(ReceivableAdvanceBatch)
            .join(ReceivableAdvanceBatchItem, ReceivableAdvanceBatchItem.batch_id == ReceivableAdvanceBatch.id)
            .where(
                ReceivableAdvanceBatchItem.invoice_id == invoice_id,
                ReceivableAdvanceBatch.status == ReceivableAdvanceBatchStatus.OPEN,
            )
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _validate_invoice_eligible(self, inv: ReceivableInvoice) -> None:
        if inv.invoice_status == "CANCELADA":
            raise ValueError(f"NF {inv.nf_number}: cancelada não pode entrar no borderô.")
        recv = float(inv.received_amount or 0)
        net = float(inv.net_amount or 0)
        if recv >= net - CENT_TOL:
            raise ValueError(f"NF {inv.nf_number}: já recebida não pode entrar no borderô.")
        ants = (
            await self.db.execute(
                select(func.count())
                .select_from(ReceivableInvoiceAnticipation)
                .where(ReceivableInvoiceAnticipation.invoice_id == inv.id)
            )
        ).scalar_one()
        if int(ants or 0) > 0:
            raise ValueError(f"NF {inv.nf_number}: já possui antecipação individual.")
        if inv.is_anticipated and inv.advance_batch_id is None:
            raise ValueError(f"NF {inv.nf_number}: já está marcada como antecipada.")
        active = await self._invoice_in_active_batch(inv.id)
        if active is not None:
            raise ValueError(
                f"NF {inv.nf_number}: já está no borderô ativo {active.batch_number}."
            )

    async def list_eligible_invoices(
        self,
        *,
        project_ids: list[UUID] | None,
        search: str | None = None,
        limit: int = 500,
    ) -> list[ReceivableInvoice]:
        active_invoice_ids = select(ReceivableAdvanceBatchItem.invoice_id).join(
            ReceivableAdvanceBatch, ReceivableAdvanceBatch.id == ReceivableAdvanceBatchItem.batch_id
        ).where(ReceivableAdvanceBatch.status == ReceivableAdvanceBatchStatus.OPEN)

        has_individual_ant = select(ReceivableInvoiceAnticipation.invoice_id).distinct()

        stmt = (
            select(ReceivableInvoice)
            .options(selectinload(ReceivableInvoice.project))
            .join(Project, Project.id == ReceivableInvoice.project_id)
            .where(
                ReceivableInvoice.invoice_status != "CANCELADA",
                ReceivableInvoice.received_amount < ReceivableInvoice.net_amount - CENT_TOL,
                ReceivableInvoice.id.not_in(has_individual_ant),
                ReceivableInvoice.id.not_in(active_invoice_ids),
                or_(ReceivableInvoice.is_anticipated.is_(False), ReceivableInvoice.advance_batch_id.is_(None)),
            )
            .order_by(ReceivableInvoice.due_date.asc(), ReceivableInvoice.nf_number.asc())
            .limit(limit)
        )
        if project_ids is not None:
            stmt = stmt.where(ReceivableInvoice.project_id.in_(project_ids))

        q = (search or "").strip().lower()
        if q:
            stmt = stmt.where(
                or_(
                    func.lower(ReceivableInvoice.nf_number).contains(q),
                    func.lower(func.coalesce(ReceivableInvoice.client_name, "")).contains(q),
                    func.lower(Project.name).contains(q),
                )
            )

        return list((await self.db.execute(stmt)).scalars().unique().all())

    async def get_batch(self, batch_id: UUID) -> ReceivableAdvanceBatch | None:
        stmt = (
            select(ReceivableAdvanceBatch)
            .where(ReceivableAdvanceBatch.id == batch_id)
            .options(
                selectinload(ReceivableAdvanceBatch.items).selectinload(ReceivableAdvanceBatchItem.invoice).selectinload(
                    ReceivableInvoice.project
                )
            )
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_batches(self, *, limit: int = 100) -> list[ReceivableAdvanceBatch]:
        stmt = (
            select(ReceivableAdvanceBatch)
            .options(
                selectinload(ReceivableAdvanceBatch.items)
                .selectinload(ReceivableAdvanceBatchItem.invoice)
                .selectinload(ReceivableInvoice.project)
            )
            .order_by(ReceivableAdvanceBatch.created_at.desc())
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().unique().all())

    async def _allocate_batch_number(self, receive_date: date) -> str:
        year = receive_date.year
        rows = (
            await self.db.execute(
                select(ReceivableAdvanceBatch.batch_number).where(
                    ReceivableAdvanceBatch.batch_number.like(f"BT-{year}-%")
                )
            )
        ).scalars().all()
        return _next_batch_number(list(rows), year=year)

    async def _ensure_payables_for_batch(
        self,
        *,
        batch_number: str,
        institution: str,
        receive_date: date,
        repayment_date: date,
        discount_amount: float,
        fee_amount: float,
    ) -> None:
        comp = normalize_competencia(receive_date)
        payables = PayableSnapshotService(self.db)
        if not await payables.is_generated(month=comp):
            await payables.get_or_create_for_month(
                payment_month=comp,
                sees_all_projects=True,
                accessible_project_ids=None,
            )

        if discount_amount > 0.005:
            await payables.create_manual(
                month=comp,
                name=f"{institution.strip()} — Deságio",
                category="Despesas financeiras",
                cost_center="Financeiro",
                amount=discount_amount,
                due_date=receive_date,
                observation=f"Operação={batch_number}",
                snapshot_type=PayableSnapshotType.ANTECIPACAO,
            )
        if fee_amount > 0.005:
            await payables.create_manual(
                month=comp,
                name=f"{institution.strip()} — Tarifas bancárias",
                category="Despesas financeiras",
                cost_center="Financeiro",
                amount=fee_amount,
                due_date=receive_date,
                observation=f"Operação={batch_number}",
                snapshot_type=PayableSnapshotType.ANTECIPACAO,
            )

    async def cancel_batch(
        self,
        *,
        batch_id: UUID,
        log_user: str | None = None,
    ) -> ReceivableAdvanceBatch:
        """
        Cancela um borderô (soft delete via status=CANCELLED), sem apagar histórico.

        - Desassocia NFs do lote
        - Remove despesas MANUAL do borderô somente se não houver pagamento nelas
        - Mantém compatibilidade com antecipação individual
        """
        batch = await self.get_batch(batch_id)
        if batch is None:
            raise ValueError("Borderô não encontrado.")
        if batch.status != ReceivableAdvanceBatchStatus.OPEN:
            raise ValueError("Apenas borderôs em aberto podem ser cancelados.")

        # Apaga despesas automáticas da operação (se não houver pagamentos registrados).
        payables = PayableSnapshotService(self.db)
        tag = _op_display_code(
            batch_number=batch.batch_number,
            operation_code=getattr(batch, "operation_code", None),
            batch_id=batch.id,
        )
        candidates = []
        for row in await payables.list_all():
            if row.type != PayableSnapshotType.ANTECIPACAO:
                continue
            name = str(getattr(row, "name", "") or "")
            obs = str(getattr(row, "observation", "") or "")
            if f"Operação={tag}" not in obs:
                continue
            if float(getattr(row, "amount_paid", 0) or 0) > 0.005:
                raise ValueError(
                    "Não é possível cancelar: despesas do borderô já possuem pagamento registrado."
                )
            candidates.append(row)

        for row in candidates:
            await payables.delete_row(row=row)

        recv_svc = ReceivableService(self.db)
        affected_months: set[date] = {
            normalize_competencia(batch.receive_date),
            normalize_competencia(batch.repayment_date),
        }

        for item in batch.items or []:
            try:
                inv = item.invoice
            except MissingGreenlet:
                inv = None
            if inv is None:
                continue
            inv.advance_batch_id = None
            if (inv.invoice_status or "").upper() not in ("CANCELADA", "RECEBIDA"):
                inv.is_anticipated = False
            if log_user:
                recv_svc.append_log(inv, f"Borderô {batch.batch_number}: cancelado by={log_user}")
            affected_months |= get_affected_months(inv)

        batch.status = ReceivableAdvanceBatchStatus.CANCELLED
        await PayableSnapshotService(self.db).invalidate_months(months=affected_months)
        await self.db.flush()
        await self.db.refresh(batch)
        return batch

    async def delete_batch(
        self,
        *,
        batch_id: UUID,
        log_user: str | None = None,
    ) -> None:
        """
        Exclusão definitiva (para correção de erro operacional).

        Regras:
        - só permite se status=CANCELLED
        - não permite se houver pagamentos nas despesas automáticas do borderô
        """
        batch = await self.get_batch(batch_id)
        if batch is None:
            raise ValueError("Borderô não encontrado.")
        if batch.status != ReceivableAdvanceBatchStatus.CANCELLED:
            raise ValueError("Para excluir definitivamente, primeiro cancele o borderô.")

        # Segurança extra: garantir que não ficou despesa com pagamento.
        tag = _op_display_code(
            batch_number=batch.batch_number,
            operation_code=getattr(batch, "operation_code", None),
            batch_id=batch.id,
        )
        payables = PayableSnapshotService(self.db)
        for row in await payables.list_all():
            if row.type != PayableSnapshotType.ANTECIPACAO:
                continue
            obs = str(getattr(row, "observation", "") or "")
            if f"Operação={tag}" not in obs:
                continue
            if float(getattr(row, "amount_paid", 0) or 0) > 0.005:
                raise ValueError("Não é possível excluir: despesas do borderô já possuem pagamento registrado.")

        # NFs deveriam estar desassociadas no cancelamento; reforça idempotência.
        recv_svc = ReceivableService(self.db)
        for item in batch.items or []:
            try:
                inv = item.invoice
            except MissingGreenlet:
                inv = None
            if inv is None:
                continue
            inv.advance_batch_id = None
            if log_user:
                recv_svc.append_log(inv, f"Borderô {batch.batch_number}: excluído definitivamente by={log_user}")

        # Remove itens e o lote
        await self.db.delete(batch)
        await self.db.flush()

    async def create_batch(
        self,
        *,
        operation_type: str = "BORDERO",
        operation_code: str | None = None,
        institution: str,
        received_amount: float,
        discount_amount: float,
        fee_amount: float,
        receive_date: date,
        repayment_date: date,
        observation: str | None,
        invoice_ids: list[UUID],
        created_by_id: UUID | None,
        log_user: str | None = None,
    ) -> ReceivableAdvanceBatch:
        unique_ids = list(dict.fromkeys(invoice_ids))
        if len(unique_ids) < 2:
            raise ValueError("Selecione no mínimo 2 notas fiscais para o borderô.")

        invoices: list[ReceivableInvoice] = []
        for iid in unique_ids:
            inv = await self.db.get(ReceivableInvoice, iid)
            if inv is None:
                raise ValueError("Uma ou mais notas fiscais não foram encontradas.")
            await self._validate_invoice_eligible(inv)
            invoices.append(inv)

        gross = round(sum(float(inv.gross_amount or 0) for inv in invoices), 2)
        if gross <= 0:
            raise ValueError("O valor bruto total das NFs deve ser positivo.")

        recv = round(float(received_amount), 2)
        disc = round(float(discount_amount), 2)
        fee = round(float(fee_amount), 2)
        if recv < 0:
            raise ValueError("Valor líquido recebido inválido.")

        batch_number = await self._allocate_batch_number(receive_date)
        batch = ReceivableAdvanceBatch(
            batch_number=batch_number,
            operation_type=str(operation_type or "BORDERO").strip() or "BORDERO",
            operation_code=(operation_code or "").strip() or None,
            institution=institution.strip(),
            gross_amount=gross,
            received_amount=recv,
            discount_amount=disc,
            fee_amount=fee,
            receive_date=receive_date,
            repayment_date=repayment_date,
            observation=(observation or "").strip() or None,
            status=ReceivableAdvanceBatchStatus.OPEN,
            created_by_id=created_by_id,
        )
        self.db.add(batch)
        await self.db.flush()

        recv_svc = ReceivableService(self.db)
        affected_months: set[date] = {normalize_competencia(receive_date), normalize_competencia(repayment_date)}

        display_code = _op_display_code(
            batch_number=batch.batch_number,
            operation_code=batch.operation_code,
            batch_id=batch.id,
        )

        for inv in invoices:
            amt = round(float(inv.gross_amount or 0), 2)
            self.db.add(
                ReceivableAdvanceBatchItem(
                    batch_id=batch.id,
                    invoice_id=inv.id,
                    invoice_amount=amt,
                )
            )
            inv.advance_batch_id = batch.id
            inv.is_anticipated = True
            inv.institution = institution.strip()
            inv.invoice_status = derive_invoice_status(
                stored_status=inv.invoice_status,
                is_anticipated=True,
                received_amount=float(inv.received_amount or 0),
                net_amount=float(inv.net_amount or 0),
            )
            if log_user:
                recv_svc.append_log(
                    inv,
                    f"Antecipação {display_code}: via lote ({institution.strip()}) by={log_user}",
                )
            affected_months |= get_affected_months(inv)

        await self._ensure_payables_for_batch(
            batch_number=display_code,
            institution=institution.strip(),
            receive_date=receive_date,
            repayment_date=repayment_date,
            discount_amount=disc,
            fee_amount=fee,
        )

        await PayableSnapshotService(self.db).invalidate_months(months=affected_months)
        await self.db.flush()
        await self.db.refresh(batch)
        return batch

    def batch_to_read(self, batch: ReceivableAdvanceBatch) -> dict:
        gross = float(batch.gross_amount or 0)
        disc = float(batch.discount_amount or 0)
        discount_percent = round((disc / gross) * 100.0, 2) if gross > 0.005 else None
        items_out: list[dict] = []
        for item in batch.items or []:
            try:
                inv = item.invoice
            except MissingGreenlet:
                inv = None
            items_out.append(
                {
                    "id": item.id,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                    "batch_id": item.batch_id,
                    "invoice_id": item.invoice_id,
                    "invoice_amount": float(item.invoice_amount),
                    "invoice_number": inv.nf_number if inv else None,
                    "client_name": inv.client_name if inv else None,
                    "project_name": (inv.project.name if inv and getattr(inv, "project", None) else None),
                    "issue_date": inv.issue_date if inv else None,
                    "due_date": inv.due_date if inv else None,
                }
            )
        return {
            "id": batch.id,
            "created_at": batch.created_at,
            "updated_at": batch.updated_at,
            "batch_number": batch.batch_number,
            "operation_type": getattr(batch, "operation_type", "BORDERO") or "BORDERO",
            "operation_code": getattr(batch, "operation_code", None),
            "institution": batch.institution,
            "gross_amount": gross,
            "received_amount": float(batch.received_amount),
            "discount_amount": disc,
            "fee_amount": float(batch.fee_amount or 0),
            "receive_date": batch.receive_date,
            "repayment_date": batch.repayment_date,
            "observation": batch.observation,
            "status": batch.status.value,
            "created_by_id": batch.created_by_id,
            "items": items_out,
            "invoice_count": len(items_out),
            "discount_percent": discount_percent,
        }

    def batch_summary(self, batch: ReceivableAdvanceBatch | None) -> dict | None:
        if batch is None:
            return None
        return {
            "id": batch.id,
            "batch_number": batch.batch_number,
            "institution": batch.institution,
            "status": batch.status.value,
        }
