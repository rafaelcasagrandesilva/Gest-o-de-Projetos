from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payable_payment import PayablePayment
from app.models.payable_snapshot import PayableSnapshot
from app.models.project import Project
from app.models.receivable import ReceivableInvoice, ReceivableInvoiceAnticipation
from app.models.receivable_advance_batch import ReceivableAdvanceBatch, ReceivableAdvanceBatchStatus
from app.models.receivable_manual import ReceivableManualItem
from app.schemas.receivable import CENT_TOL
from app.utils.date_utils import normalize_competencia, previous_competencia

logger = logging.getLogger(__name__)


def _merge_month_amounts(*maps: dict[date, float]) -> dict[date, float]:
    keys: set[date] = set()
    for m in maps:
        keys |= set(m.keys())
    out: dict[date, float] = {}
    for k in keys:
        out[k] = round(sum(float(m.get(k, 0.0)) for m in maps), 2)
    return out


def _month_bounds(comp: date) -> tuple[date, date]:
    c = normalize_competencia(comp)
    last = calendar.monthrange(c.year, c.month)[1]
    return date(c.year, c.month, 1), date(c.year, c.month, last)


def _iter_months(start: date, end: date) -> list[date]:
    s = normalize_competencia(start)
    e = normalize_competencia(end)
    out: list[date] = []
    cur = s
    while cur <= e:
        out.append(cur)
        cur = date(cur.year + 1, 1, 1) if cur.month == 12 else date(cur.year, cur.month + 1, 1)
    return out


@dataclass(frozen=True)
class CashDashboardSummary:
    month: date
    period_start: date
    period_end: date
    faturamento: float
    pago: float
    caixa: float


@dataclass(frozen=True)
class CashDashboardPoint:
    month: date
    faturamento: float
    pago: float
    caixa: float


@dataclass(frozen=True)
class CashDashboardGroup:
    label: str
    valor: float


def _merge_cash_groups(*group_lists: list[list[CashDashboardGroup]]) -> list[CashDashboardGroup]:
    acc: dict[str, float] = {}
    for gl in group_lists:
        for g in gl:
            acc[g.label] = round(acc.get(g.label, 0.0) + g.valor, 2)
    out = [CashDashboardGroup(label=k, valor=v) for k, v in acc.items()]
    out.sort(key=lambda x: -x.valor)
    return out


class FinancialDashboardService:
    """
    Dashboard financeiro em regime de caixa:
    - Faturamento: total recebido no mês (data de recebimento), alinhado a Contas a receber:
      notas fiscais (`received_date` + valor recebido) e receitas manuais (`data_recebimento` + valor recebido).
    - Custos: pago (contas a pagar), agrupado por mês da data real do pagamento (`PayablePayment.payment_date`)
    - Caixa: faturamento - custos
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def cash_summary_and_series(
        self, *, month: date, months: int, workspace_id: str = "finance"
    ) -> tuple[CashDashboardSummary, list[CashDashboardPoint]]:
        end = normalize_competencia(month)
        start = end
        for _ in range(max(0, months - 1)):
            start = previous_competencia(start)

        months_list = _iter_months(start, end)
        period_start, _ = _month_bounds(start)
        _, period_end = _month_bounds(end)

        # --- Faturamento (cliente) por mês (received_date) ---
        rev_stmt = (
            select(
                func.date_trunc("month", ReceivableInvoice.received_date).label("m"),
                func.coalesce(func.sum(ReceivableInvoice.received_amount), 0).label("v"),
            )
            .where(
                ReceivableInvoice.invoice_status != "CANCELADA",
                ReceivableInvoice.received_date.is_not(None),
                ReceivableInvoice.received_date >= period_start,
                ReceivableInvoice.received_date <= period_end,
                ReceivableInvoice.received_amount > 0,
                # coerência com status RECEBIDA (binário no sistema): recebido >= net - tol
                ReceivableInvoice.received_amount >= (ReceivableInvoice.net_amount - CENT_TOL),
            )
            .group_by("m")
        )
        rev_rows = (await self.db.execute(rev_stmt)).all()
        rev_map_nf = {normalize_competencia(r.m.date()): float(r.v) for r in rev_rows if r.m is not None}

        # Antecipações (entrada de caixa no dia do recebimento da antecipação)
        ant_stmt = (
            select(
                func.date_trunc("month", ReceivableInvoiceAnticipation.received_date).label("m"),
                func.coalesce(func.sum(ReceivableInvoiceAnticipation.amount_received), 0).label("v"),
            )
            .where(
                ReceivableInvoiceAnticipation.received_date.is_not(None),
                ReceivableInvoiceAnticipation.received_date >= period_start,
                ReceivableInvoiceAnticipation.received_date <= period_end,
                ReceivableInvoiceAnticipation.amount_received > 0,
            )
            .group_by("m")
        )
        ant_rows = (await self.db.execute(ant_stmt)).all()
        rev_map_ants = {normalize_competencia(r.m.date()): float(r.v) for r in ant_rows if r.m is not None}

        # Borderôs (entrada líquida no mês do recebimento)
        batch_stmt = (
            select(
                func.date_trunc("month", ReceivableAdvanceBatch.receive_date).label("m"),
                func.coalesce(func.sum(ReceivableAdvanceBatch.received_amount), 0).label("v"),
            )
            .where(
                ReceivableAdvanceBatch.status != ReceivableAdvanceBatchStatus.CANCELLED,
                ReceivableAdvanceBatch.receive_date >= period_start,
                ReceivableAdvanceBatch.receive_date <= period_end,
                ReceivableAdvanceBatch.received_amount > 0,
            )
            .group_by("m")
        )
        batch_rows = (await self.db.execute(batch_stmt)).all()
        rev_map_batches = {normalize_competencia(r.m.date()): float(r.v) for r in batch_rows if r.m is not None}

        # Receitas manuais (mesma lógica da tela Contas a receber — tipo MANUAL)
        man_stmt = (
            select(
                func.date_trunc("month", ReceivableManualItem.data_recebimento).label("m"),
                func.coalesce(func.sum(ReceivableManualItem.valor_recebido), 0).label("v"),
            )
            .where(
                ReceivableManualItem.workspace_id == workspace_id,
                ReceivableManualItem.data_recebimento.is_not(None),
                ReceivableManualItem.data_recebimento >= period_start,
                ReceivableManualItem.data_recebimento <= period_end,
                ReceivableManualItem.valor_recebido > 0,
                ReceivableManualItem.valor_recebido >= (ReceivableManualItem.valor_liquido - CENT_TOL),
            )
            .group_by("m")
        )
        man_rows = (await self.db.execute(man_stmt)).all()
        rev_map_manual = {normalize_competencia(r.m.date()): float(r.v) for r in man_rows if r.m is not None}
        rev_map = _merge_month_amounts(rev_map_nf, rev_map_ants, rev_map_batches, rev_map_manual)

        # --- Pago (fluxo de caixa real) por mês da data do pagamento ---
        pay_month = func.date_trunc("month", PayablePayment.payment_date).label("m")
        cost_stmt = (
            select(
                pay_month,
                func.coalesce(func.sum(PayablePayment.amount), 0).label("v"),
            )
            .where(
                PayablePayment.reversed_at.is_(None),
                PayablePayment.payment_date >= period_start,
                PayablePayment.payment_date <= period_end,
            )
            .group_by("m")
        )
        cost_rows = (await self.db.execute(cost_stmt)).all()
        cost_map = {normalize_competencia(r.m): float(r.v) for r in cost_rows if r.m is not None}

        # Série mensal
        points: list[CashDashboardPoint] = []
        for m in months_list:
            fat = round(float(rev_map.get(m, 0.0)), 2)
            pago = round(float(cost_map.get(m, 0.0)), 2)
            caixa = round(fat - pago, 2)
            points.append(CashDashboardPoint(month=m, faturamento=fat, pago=pago, caixa=caixa))

        faturamento = round(sum(p.faturamento for p in points), 2)
        pago = round(sum(p.pago for p in points), 2)
        caixa = round(faturamento - pago, 2)
        # Garantia de consistência: caixa == recebido - pago
        expected = round(faturamento - pago, 2)
        if caixa != expected:
            logger.error("dashboard cash mismatch month=%s months=%s faturamento=%s pago=%s caixa=%s expected=%s", end, months, faturamento, pago, caixa, expected)
            caixa = expected

        summary = CashDashboardSummary(
            month=end,
            period_start=start,
            period_end=end,
            faturamento=faturamento,
            pago=pago,
            caixa=caixa,
        )
        return summary, points

    async def cash_breakdown(
        self, *, type: str, month: date, workspace_id: str = "finance"
    ) -> tuple[
        float,
        list[CashDashboardGroup],
        float | None,
        list[CashDashboardGroup] | None,
        float | None,
        list[CashDashboardGroup] | None,
    ]:
        comp = normalize_competencia(month)
        start, end = _month_bounds(comp)

        if type == "faturamento":
            stmt_nf = (
                select(
                    Project.name.label("label"),
                    func.coalesce(func.sum(ReceivableInvoice.received_amount), 0).label("v"),
                )
                .select_from(ReceivableInvoice)
                .join(Project, Project.id == ReceivableInvoice.project_id)
                .where(
                    ReceivableInvoice.invoice_status != "CANCELADA",
                    ReceivableInvoice.received_date.is_not(None),
                    ReceivableInvoice.received_date >= start,
                    ReceivableInvoice.received_date <= end,
                    ReceivableInvoice.received_amount > 0,
                    ReceivableInvoice.received_amount >= (ReceivableInvoice.net_amount - CENT_TOL),
                )
                .group_by(Project.name)
                .order_by(func.sum(ReceivableInvoice.received_amount).desc())
            )
            rows_nf = (await self.db.execute(stmt_nf)).all()
            groups_nf = [CashDashboardGroup(label=str(r.label), valor=round(float(r.v), 2)) for r in rows_nf]

            stmt_man = (
                select(
                    ReceivableManualItem.cliente.label("label"),
                    func.coalesce(func.sum(ReceivableManualItem.valor_recebido), 0).label("v"),
                )
                .where(
                    ReceivableManualItem.workspace_id == workspace_id,
                    ReceivableManualItem.data_recebimento.is_not(None),
                    ReceivableManualItem.data_recebimento >= start,
                    ReceivableManualItem.data_recebimento <= end,
                    ReceivableManualItem.valor_recebido > 0,
                    ReceivableManualItem.valor_recebido >= (ReceivableManualItem.valor_liquido - CENT_TOL),
                )
                .group_by(ReceivableManualItem.cliente)
                .order_by(func.sum(ReceivableManualItem.valor_recebido).desc())
            )
            rows_man = (await self.db.execute(stmt_man)).all()
            groups_man = [CashDashboardGroup(label=str(r.label), valor=round(float(r.v), 2)) for r in rows_man]

            groups = _merge_cash_groups(groups_nf, groups_man)
            total = round(sum(g.valor for g in groups), 2)
            return total, groups, None, None, None, None

        if type == "custos":
            stmt = (
                select(
                    PayableSnapshot.cost_center.label("label"),
                    func.coalesce(func.sum(PayablePayment.amount), 0).label("v"),
                )
                .select_from(PayablePayment)
                .join(PayableSnapshot, PayableSnapshot.id == PayablePayment.payable_snapshot_id)
                .where(
                    PayablePayment.reversed_at.is_(None),
                    PayablePayment.payment_date >= start,
                    PayablePayment.payment_date <= end,
                )
                .group_by(PayableSnapshot.cost_center)
                .order_by(func.sum(PayablePayment.amount).desc())
            )
            rows = (await self.db.execute(stmt)).all()
            groups = [CashDashboardGroup(label=str(r.label), valor=round(float(r.v), 2)) for r in rows]
            total = round(sum(g.valor for g in groups), 2)
            return total, groups, None, None, None, None

        # caixa = faturamento - custos
        fat_total, fat_groups, _, _, _, _ = await self.cash_breakdown(
            type="faturamento", month=comp, workspace_id=workspace_id
        )
        cus_total, cus_groups, _, _, _, _ = await self.cash_breakdown(type="custos", month=comp)
        total = round(fat_total - cus_total, 2)
        return total, [], fat_total, fat_groups, cus_total, cus_groups

