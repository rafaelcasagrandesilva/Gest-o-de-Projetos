from __future__ import annotations

import calendar
import logging
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid4

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.scenario import Scenario, coerce_scenario, scenario_pg_rhs
from app.models.costs import ProjectFixedCost
from app.models.company_finance import CompanyFinancialItem, CompanyFinancialPayment
from app.models.employee_monthly_payroll_override import EmployeeMonthlyPayrollOverride
from app.models.payable_payment import PayablePayment
from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
from app.models.payable_snapshot_generation import PayableSnapshotGeneration
from app.models.project_operational import (
    ProjectLabor,
    ProjectOperationalFixed,
    ProjectSystemCost,
    ProjectVehicle,
)
from app.models.receivable import ReceivableInvoice, ReceivableInvoiceAnticipation
from app.repositories.projects import ProjectRepository
from app.models.project import Project
from app.services.company_finance_cost_center import CompanyFinanceCostCenterService
from app.services.employee_cost_service import project_labor_payable_snapshot_components
from app.services.settings_service import SettingsService
from app.utils.date_utils import next_competencia, normalize_competencia, previous_competencia

logger = logging.getLogger(__name__)

PAYABLE_PAYMENT_TOLERANCE = Decimal("0.02")
_MONEY_QUANT = Decimal("0.01")
PAYABLE_MANUAL_ADJUSTMENT_TAG = "[ajuste manual]"
PAYABLE_CONCILIATED_TAG = "[conciliado]"


def _money2(value: object) -> Decimal:
    """Valor monetário com 2 casas — evita comparações quebradas por float / Numeric impreciso."""
    if value is None:
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)
    return Decimal(str(round(float(value), 2))).quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)


# Contas a pagar — despesa manual (centros fixos + nome de projeto cadastrado)
MANUAL_PAYABLE_FIXED_COST_CENTERS = frozenset({"Administrativo", "Financeiro"})
PAYABLE_DEBT_TYPES = (PayableSnapshotType.ENDIVIDAMENTO, PayableSnapshotType.FINANCIAL)

SOURCE_TAG_PROJECT_MISC = "[source:project_misc_cost]"
SOURCE_TAG_PROJECT_SYSTEM = "[source:project_system]"
CATEGORY_PROJECT_MISC = "Custo diverso"
CATEGORY_PROJECT_SYSTEM = "Sistema"


def _project_item_snapshot_name(item_name: str, *, fallback: str = "Item") -> str:
    """Nome exibido no payable — sem prefixo (tipo/categoria já identificam)."""
    return (item_name or "").strip() or fallback


def payable_snapshot_payment_status(*, amount_paid: Decimal, amount_final: Decimal) -> str:
    """ABERTO | PARCIAL | PAGO (inclui overpayment como PAGO)."""
    ap = _money2(amount_paid)
    af = _money2(amount_final)
    if ap <= 0:
        return "ABERTO"
    if ap + PAYABLE_PAYMENT_TOLERANCE < af:
        return "PARCIAL"
    return "PAGO"


def payable_snapshot_derived_fields(*, amount_paid: Decimal, amount_final: Decimal) -> dict[str, object]:
    """
    Campos derivados para API/UI.

    amount_remaining pode ser negativo (adiantamento/overpayment).
    """
    ap = _money2(amount_paid)
    af = _money2(amount_final)
    remaining = (af - ap).quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)
    is_overpaid = ap > af + PAYABLE_PAYMENT_TOLERANCE
    overpaid_amount = (
        (ap - af).quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP) if is_overpaid else Decimal("0.00")
    )
    return {
        "amount_remaining": float(remaining),
        "is_overpaid": is_overpaid,
        "overpaid_amount": float(overpaid_amount),
        "status": payable_snapshot_payment_status(amount_paid=ap, amount_final=af),
    }


def _payable_row_is_protected_from_auto_delete(row: PayableSnapshot) -> bool:
    """MANUAL ou já com pagamento registrado — nunca remover no sync corporativo."""
    if row.type == PayableSnapshotType.MANUAL:
        return True
    return _money2(row.amount_paid) > 0


def _payable_row_is_dynamic_sync_protected(row: PayableSnapshot) -> bool:
    """Snapshots que não devem ter valores recalculados automaticamente."""
    if row.type == PayableSnapshotType.MANUAL:
        return True
    obs = (row.observation or "").casefold()
    if PAYABLE_MANUAL_ADJUSTMENT_TAG.casefold() in obs:
        return True
    if PAYABLE_CONCILIATED_TAG.casefold() in obs:
        return True
    if abs(_money2(row.amount_final) - _money2(row.amount_original)) > PAYABLE_PAYMENT_TOLERANCE:
        return True
    return False


async def _has_active_payments(session: AsyncSession, *, snapshot_id: UUID) -> bool:
    cnt = (
        await session.execute(
            select(func.count())
            .select_from(PayablePayment)
            .where(
                PayablePayment.payable_snapshot_id == snapshot_id,
                PayablePayment.reversed_at.is_(None),
            )
        )
    ).scalar_one()
    return int(cnt or 0) > 0


def _payable_remaining_balance(*, amount_final: Decimal, amount_paid: Decimal) -> Decimal:
    """Saldo assinado: negativo quando overpaid."""
    return (_money2(amount_final) - _money2(amount_paid)).quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)


def _apply_dynamic_payable_amounts(row: PayableSnapshot, *, new_amount: Decimal) -> None:
    """Atualiza obrigação preservando amount_paid e recalcula status legado."""
    row.amount_original = new_amount
    row.amount_final = new_amount
    _sync_legacy_paid_fields(row)


def _log_payable_dynamic_sync(
    *,
    action: str,
    row: PayableSnapshot,
    before_original: Decimal,
    before_final: Decimal,
    before_paid: Decimal,
) -> None:
    after_final = _money2(row.amount_final)
    after_paid = _money2(row.amount_paid)
    derived = payable_snapshot_derived_fields(amount_paid=after_paid, amount_final=after_final)
    logger.info(
        "payables dynamic sync %s snapshot_id=%s name=%s before_original=%s before_final=%s "
        "before_paid=%s after_final=%s amount_paid=%s saldo=%s status=%s is_overpaid=%s overpaid_amount=%s",
        action,
        row.id,
        row.name,
        before_original,
        before_final,
        before_paid,
        after_final,
        after_paid,
        derived["amount_remaining"],
        derived["status"],
        derived["is_overpaid"],
        derived["overpaid_amount"],
    )
    if derived["is_overpaid"]:
        logger.warning(
            "payables dynamic sync reconciliation overpaid snapshot_id=%s name=%s saldo=%s overpaid_amount=%s",
            row.id,
            row.name,
            derived["amount_remaining"],
            derived["overpaid_amount"],
        )


def _sync_legacy_paid_fields(row: PayableSnapshot, *, anchor_date: date | None = None) -> None:
    """Mantém `paid` / `payment_date` coerentes com `amount_paid` (legado / relatórios)."""
    st = payable_snapshot_payment_status(
        amount_paid=_money2(row.amount_paid),
        amount_final=_money2(row.amount_final),
    )
    if st == "PAGO":
        row.paid = True
        row.payment_date = anchor_date or date.today()
    else:
        row.paid = False
        row.payment_date = None


def _validate_payment_date(payment_date: date | None) -> date:
    pd = payment_date or date.today()
    if pd > date.today():
        raise ValueError("Data do pagamento não pode ser futura.")
    return pd


def _payable_snapshot_open_sql():
    """Obrigação ainda não quitada (ABERTO ou PARCIAL)."""
    return or_(
        PayableSnapshot.amount_paid <= 0,
        PayableSnapshot.amount_paid + PAYABLE_PAYMENT_TOLERANCE < PayableSnapshot.amount_final,
    )


def _default_due_date(payment_month: date, *, day: int = 10) -> date:
    comp = normalize_competencia(payment_month)
    last = calendar.monthrange(comp.year, comp.month)[1]
    return date(comp.year, comp.month, min(max(day, 1), last))


def _month_bounds(comp: date) -> tuple[date, date]:
    c = normalize_competencia(comp)
    last = calendar.monthrange(c.year, c.month)[1]
    return date(c.year, c.month, 1), date(c.year, c.month, last)


def _competence_month_yyyy_mm(comp: date) -> str:
    c = normalize_competencia(comp)
    return f"{c.year:04d}-{c.month:02d}"


def _collaborator_payable_snapshot_name(display_name: str, component_label: str) -> str:
    label = (component_label or "").strip()
    if not label:
        return display_name
    return f"{display_name} — {label}"


def _allocate_payable_components(
    components: list[tuple[str, float]], factor: float
) -> list[tuple[str, float]]:
    """Rateia componentes pelo % do projeto; última linha absorve centavos de arredondamento."""
    if not components or factor <= 0:
        return []
    integral_total = sum(amt for _, amt in components)
    target_total = round(integral_total * factor, 2)
    if target_total <= 0:
        return []

    if len(components) == 1:
        return [(components[0][0], target_total)]

    out: list[tuple[str, float]] = []
    allocated = 0.0
    for idx, (label, integral_amt) in enumerate(components):
        if idx == len(components) - 1:
            amt = round(target_total - allocated, 2)
        else:
            amt = round(integral_amt * factor, 2)
            allocated += amt
        if amt > 0:
            out.append((label, amt))
    return out


def _employee_display_name(emp: object) -> str:
    """Rótulo do colaborador no snapshot; o model `Employee` usa `full_name`, não `name`."""
    for attr in ("full_name", "name", "nome"):
        v = getattr(emp, attr, None)
        if v is not None and str(v).strip():
            return str(v).strip()
    email = getattr(emp, "email", None)
    if email is not None and str(email).strip():
        return str(email).strip()
    eid = getattr(emp, "id", None)
    return f"Colaborador ({eid})" if eid is not None else "Colaborador"


def _project_cost_center_label(project: Project) -> str:
    cc = getattr(project, "cost_center", None)
    if cc is not None and str(cc).strip():
        return str(cc).strip()
    return str(project.name).strip()


class PayableSnapshotService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _payroll_override_map_for_month(
        self, *, employee_ids: list[UUID], source_month: date
    ) -> dict[UUID, EmployeeMonthlyPayrollOverride]:
        if not employee_ids:
            return {}
        comp = _competence_month_yyyy_mm(source_month)
        rows = (
            (
                await self.session.execute(
                    select(EmployeeMonthlyPayrollOverride).where(
                        EmployeeMonthlyPayrollOverride.employee_id.in_(employee_ids),
                        EmployeeMonthlyPayrollOverride.competence_month == comp,
                    )
                )
            )
            .scalars()
            .all()
        )
        return {r.employee_id: r for r in rows}

    async def _count_paid_automatic_rows(self, *, month: date) -> int:
        comp = normalize_competencia(month)
        return int(
            (
                await self.session.scalar(
                    select(func.count())
                    .select_from(PayableSnapshot)
                    .where(
                        PayableSnapshot.month == comp,
                        PayableSnapshot.type != PayableSnapshotType.MANUAL,
                        PayableSnapshot.amount_paid > 0,
                    )
                )
            )
            or 0
        )

    async def invalidate_months(self, *, months: set[date] | list[date] | tuple[date, ...]) -> int:
        """
        Invalida snapshots do(s) mês(es): remove linhas geradas automaticamente e o marcador.

        Despesas **MANUAIS** (lançadas em Contas a pagar) **não** são apagadas — evita perda ao
        invalidar por NF/recebíveis/estrutura. Na próxima abertura do mês, o snapshot é regerado
        em cima das MANUAIS preservadas.

        Retorna quantidade de meses efetivamente processados.
        """
        if not months:
            return 0
        comps = sorted({normalize_competencia(m) for m in months})
        processed = 0
        for comp in comps:
            paid_rows = await self._count_paid_automatic_rows(month=comp)
            if paid_rows > 0:
                logger.error(
                    "refusing to invalidate payable snapshot month=%s because it has %d paid automatic rows",
                    comp,
                    paid_rows,
                )
                continue
            await self.session.execute(
                delete(PayableSnapshot).where(
                    PayableSnapshot.month == comp,
                    PayableSnapshot.type != PayableSnapshotType.MANUAL,
                )
            )
            await self.session.execute(text("DELETE FROM payable_snapshot_generations WHERE month = :m"), {"m": comp})
            processed += 1
        await self.session.flush()
        return processed

    async def list_generated_months(self) -> list[date]:
        stmt = select(PayableSnapshotGeneration.month).order_by(PayableSnapshotGeneration.month.asc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_for_month(self, *, month: date) -> list[PayableSnapshot]:
        comp = normalize_competencia(month)
        stmt = select(PayableSnapshot).where(PayableSnapshot.month == comp).order_by(
            PayableSnapshot.type.asc(), PayableSnapshot.cost_center.asc(), PayableSnapshot.name.asc()
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_for_operational_month(self, *, month: date) -> list[PayableSnapshot]:
        """
        Visão operacional do mês (competência + fluxo de caixa):

        A) todas as obrigações da competência do mês (`snapshot.month` = mês filtrado)
        B) obrigações com pagamento realizado no mês (`payment_date` no intervalo), qualquer competência

        União sem duplicar por snapshot.id.
        """
        comp = normalize_competencia(month)
        start, end = _month_bounds(comp)

        competence_stmt = (
            select(PayableSnapshot)
            .where(PayableSnapshot.month == comp)
            .order_by(
                PayableSnapshot.due_date.asc(),
                PayableSnapshot.type.asc(),
                PayableSnapshot.name.asc(),
            )
        )
        competence_rows = list((await self.session.execute(competence_stmt)).scalars().all())

        paid_ids = set(
            (
                await self.session.execute(
                    select(PayablePayment.payable_snapshot_id)
                    .where(
                        PayablePayment.reversed_at.is_(None),
                        PayablePayment.payment_date >= start,
                        PayablePayment.payment_date <= end,
                    )
                    .distinct()
                )
            )
            .scalars()
            .all()
        )

        paid_rows: list[PayableSnapshot] = []
        if paid_ids:
            paid_stmt = (
                select(PayableSnapshot)
                .where(PayableSnapshot.id.in_(paid_ids))
                .order_by(
                    PayableSnapshot.month.asc(),
                    PayableSnapshot.due_date.asc(),
                    PayableSnapshot.name.asc(),
                )
            )
            paid_rows = list((await self.session.execute(paid_stmt)).scalars().all())

        merged: dict[UUID, PayableSnapshot] = {r.id: r for r in competence_rows}
        for r in paid_rows:
            merged.setdefault(r.id, r)

        return list(merged.values())

    async def paid_in_period_by_snapshot_ids(
        self, snapshot_ids: list[UUID], *, month: date
    ) -> dict[UUID, Decimal]:
        """Soma de pagamentos ativos com payment_date no mês (fluxo de caixa do período)."""
        if not snapshot_ids:
            return {}
        comp = normalize_competencia(month)
        start, end = _month_bounds(comp)
        stmt = (
            select(
                PayablePayment.payable_snapshot_id,
                func.coalesce(func.sum(PayablePayment.amount), 0),
            )
            .where(
                PayablePayment.payable_snapshot_id.in_(snapshot_ids),
                PayablePayment.reversed_at.is_(None),
                PayablePayment.payment_date >= start,
                PayablePayment.payment_date <= end,
            )
            .group_by(PayablePayment.payable_snapshot_id)
        )
        rows = (await self.session.execute(stmt)).all()
        return {sid: _money2(amt) for sid, amt in rows}

    async def list_all(self) -> list[PayableSnapshot]:
        stmt = select(PayableSnapshot).order_by(
            PayableSnapshot.month.desc(),
            PayableSnapshot.type.asc(),
            PayableSnapshot.cost_center.asc(),
            PayableSnapshot.name.asc(),
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get(self, snapshot_id: UUID) -> PayableSnapshot | None:
        return await self.session.get(PayableSnapshot, snapshot_id)

    async def last_payment_dates_by_snapshot_ids(self, snapshot_ids: list[UUID]) -> dict[UUID, date]:
        if not snapshot_ids:
            return {}
        stmt = (
            select(
                PayablePayment.payable_snapshot_id,
                func.max(PayablePayment.payment_date),
            )
            .where(
                PayablePayment.payable_snapshot_id.in_(snapshot_ids),
                PayablePayment.reversed_at.is_(None),
            )
            .group_by(PayablePayment.payable_snapshot_id)
        )
        rows = (await self.session.execute(stmt)).all()
        return {sid: d for sid, d in rows if d is not None}

    async def _sum_active_payments(self, snapshot_id: UUID) -> Decimal:
        total = await self.session.scalar(
            select(func.coalesce(func.sum(PayablePayment.amount), 0)).where(
                PayablePayment.payable_snapshot_id == snapshot_id,
                PayablePayment.reversed_at.is_(None),
            )
        )
        return _money2(total or 0)

    async def _max_active_payment_date(self, snapshot_id: UUID) -> date | None:
        return await self.session.scalar(
            select(func.max(PayablePayment.payment_date)).where(
                PayablePayment.payable_snapshot_id == snapshot_id,
                PayablePayment.reversed_at.is_(None),
            )
        )

    async def _list_active_payments(
        self, snapshot_id: UUID, *, newest_first: bool = True
    ) -> list[PayablePayment]:
        stmt = select(PayablePayment).where(
            PayablePayment.payable_snapshot_id == snapshot_id,
            PayablePayment.reversed_at.is_(None),
        )
        if newest_first:
            stmt = stmt.order_by(
                PayablePayment.payment_date.desc(),
                PayablePayment.created_at.desc(),
            )
        else:
            stmt = stmt.order_by(
                PayablePayment.payment_date.asc(),
                PayablePayment.created_at.asc(),
            )
        return list((await self.session.execute(stmt)).scalars().all())

    async def _recalculate_amount_paid(self, row: PayableSnapshot) -> None:
        total = await self._sum_active_payments(row.id)
        row.amount_paid = total
        anchor = await self._max_active_payment_date(row.id)
        _sync_legacy_paid_fields(row, anchor_date=anchor)

    async def count_for_month(self, *, month: date) -> int:
        comp = normalize_competencia(month)
        stmt = select(func.count()).select_from(PayableSnapshot).where(PayableSnapshot.month == comp)
        return int((await self.session.execute(stmt)).scalar_one())

    async def is_generated(self, *, month: date) -> bool:
        comp = normalize_competencia(month)
        row = await self.session.get(PayableSnapshotGeneration, comp)
        return row is not None

    async def _ensure_company_finance_manual_entries(self, *, payment_month: date) -> int:
        """
        Garante que lançamentos corporativos (custos diversos + endividamento) existam no snapshot do mês
        SOMENTE quando houver valor preenchido manualmente em `company_financial_payments` para a competência.
        """
        comp = normalize_competencia(payment_month)
        due = _default_due_date(comp, day=10)
        rows = (
            await self.session.execute(
                select(CompanyFinancialPayment, CompanyFinancialItem)
                .join(CompanyFinancialItem, CompanyFinancialItem.id == CompanyFinancialPayment.item_id)
                .where(
                    CompanyFinancialPayment.competencia == comp,
                    CompanyFinancialPayment.valor > 0,
                    CompanyFinancialItem.tipo.in_(("custo_fixo", "endividamento")),
                )
            )
        ).all()
        if not rows:
            return 0

        item_ids = [it.id for _, it in rows]
        existing_fixed = set(
            (
                await self.session.execute(
                    select(PayableSnapshot.ref_id).where(
                        PayableSnapshot.month == comp,
                        PayableSnapshot.type == PayableSnapshotType.FIXED_COST,
                        PayableSnapshot.ref_id.in_(item_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        existing_fin = set(
            (
                await self.session.execute(
                    select(PayableSnapshot.ref_id).where(
                        PayableSnapshot.month == comp,
                        PayableSnapshot.type.in_(PAYABLE_DEBT_TYPES),
                        PayableSnapshot.ref_id.in_(item_ids),
                    )
                )
            )
            .scalars()
            .all()
        )

        created = 0
        for p, it in rows:
            amt = float(p.valor or 0.0)
            if amt <= 0:
                continue
            snap_type, cost_center, category = await self._company_finance_snapshot_meta(it)
            if it.tipo == "custo_fixo":
                if it.id in existing_fixed:
                    continue
            else:
                if it.id in existing_fin:
                    continue

            self.session.add(
                PayableSnapshot(
                    month=comp,
                    type=snap_type,
                    ref_id=it.id,
                    project_id=None,
                    name=str(it.nome).strip(),
                    cost_center=cost_center,
                    category=category,
                    amount_original=Decimal(str(round(amt, 2))),
                    amount_final=Decimal(str(round(amt, 2))),
                    amount_paid=Decimal("0"),
                    due_date=due,
                    paid=False,
                    payment_date=None,
                    observation=None,
                )
            )
            created += 1

        if created:
            logger.warning("payables company_finance manual entries backfill applied month=%s added=%d", comp, created)
        return created

    async def _get_company_financial_item(self, item_id: UUID) -> CompanyFinancialItem | None:
        """Carrega item sem lazy load async (cost_center_project via selectinload)."""
        stmt = (
            select(CompanyFinancialItem)
            .where(CompanyFinancialItem.id == item_id)
            .options(selectinload(CompanyFinancialItem.cost_center_project))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _company_finance_snapshot_meta(self, item: CompanyFinancialItem) -> tuple[PayableSnapshotType, str, str]:
        cc_svc = CompanyFinanceCostCenterService(self.session)
        # Nunca passar item.cost_center_project: acesso lazy quebra greenlet no async.
        cost_center = await cc_svc.resolve_label(item)
        if item.tipo == "custo_fixo":
            category = str(getattr(item, "category", None) or "Custos diversos").strip()
            return PayableSnapshotType.FIXED_COST, cost_center, category
        if item.tipo == "endividamento":
            category = str(getattr(item, "category", None) or "Endividamento").strip()
            return PayableSnapshotType.ENDIVIDAMENTO, cost_center, category
        raise ValueError("Tipo financeiro corporativo inválido para contas a pagar.")

    async def sync_company_finance_item_metadata(self, *, item_id: UUID) -> int:
        """
        Atualiza nome/centro/categoria em snapshots corporativos existentes.

        Nunca apaga linhas nem altera valores (`amount_*`). Usado em edição estrutural.
        """
        item = await self._get_company_financial_item(item_id)
        if item is None:
            return 0
        _snap_type, cost_center, category = await self._company_finance_snapshot_meta(item)
        rows = (
            await self.session.execute(
                select(PayableSnapshot).where(
                    PayableSnapshot.ref_id == item_id,
                    PayableSnapshot.type.in_((PayableSnapshotType.FIXED_COST, *PAYABLE_DEBT_TYPES)),
                )
            )
        ).scalars().all()
        for row in rows:
            row.name = str(item.nome).strip()
            row.cost_center = cost_center
            row.category = category
            _sync_legacy_paid_fields(row)
        await self.session.flush()
        return len(rows)

    async def sync_company_finance_item_months(self, *, item_id: UUID, months: set[date]) -> int:
        """
        Sincroniza valores de payables a partir de `company_financial_payments` (Salvar agora).

        Não invalida nem recria o snapshot do mês inteiro. Remove linhas não pagas (exceto MANUAL)
        quando o pagamento corporativo do mês zera. Linhas pagas nunca são apagadas.
        """
        if not months:
            return 0

        item = await self._get_company_financial_item(item_id)
        if item is None:
            return 0
        snap_type, cost_center, category = await self._company_finance_snapshot_meta(item)
        comps = sorted({normalize_competencia(m) for m in months})
        pay_rows = (
            await self.session.execute(
                select(CompanyFinancialPayment).where(
                    CompanyFinancialPayment.item_id == item_id,
                    CompanyFinancialPayment.competencia.in_(comps),
                )
            )
        ).scalars().all()
        payments_by_month = {normalize_competencia(p.competencia): _money2(p.valor) for p in pay_rows}

        changed = 0
        for comp in comps:
            existing = list(
                (
                    await self.session.execute(
                        select(PayableSnapshot).where(
                            PayableSnapshot.month == comp,
                            PayableSnapshot.ref_id == item_id,
                            PayableSnapshot.type.in_((PayableSnapshotType.FIXED_COST, *PAYABLE_DEBT_TYPES)),
                        )
                    )
                )
                .scalars()
                .all()
            )
            # Sem marcador de geração e sem linha existente: aguarda geração do mês.
            if not existing and not await self.is_generated(month=comp):
                logger.info(
                    "payables company_finance sync skip item_id=%s month=%s (month not generated, no rows)",
                    item_id,
                    comp,
                )
                continue

            amount = payments_by_month.get(comp, Decimal("0.00"))

            if amount <= 0:
                removed = 0
                protected = 0
                for row in existing:
                    if _payable_row_is_protected_from_auto_delete(row):
                        row.name = str(item.nome).strip()
                        row.cost_center = cost_center
                        row.category = category
                        _sync_legacy_paid_fields(row)
                        protected += 1
                        changed += 1
                        continue
                    await self.session.delete(row)
                    removed += 1
                    changed += 1
                logger.info(
                    "payables company_finance sync zero amount item_id=%s month=%s removed=%d protected=%d",
                    item_id,
                    comp,
                    removed,
                    protected,
                )
                continue

            target = next((row for row in existing if row.type == snap_type), None)
            if target is None:
                target = PayableSnapshot(
                    month=comp,
                    type=snap_type,
                    ref_id=item.id,
                    project_id=None,
                    name=str(item.nome).strip(),
                    cost_center=cost_center,
                    category=category,
                    amount_original=amount,
                    amount_final=amount,
                    amount_paid=Decimal("0"),
                    due_date=_default_due_date(comp, day=10),
                    paid=False,
                    payment_date=None,
                    observation=None,
                )
                self.session.add(target)
                changed += 1

            if _money2(target.amount_paid) > 0:
                _sync_legacy_paid_fields(target)
                continue

            target.name = str(item.nome).strip()
            target.cost_center = cost_center
            target.category = category
            target.amount_original = amount
            target.amount_final = amount
            target.due_date = _default_due_date(comp, day=10)
            _sync_legacy_paid_fields(target)

            for row in existing:
                if row.id == target.id:
                    continue
                if _payable_row_is_protected_from_auto_delete(row):
                    _sync_legacy_paid_fields(row)
                    continue
                await self.session.delete(row)
                changed += 1

        await self.session.flush()
        return changed

    async def sync_collaborator_payables_for_labor(
        self,
        *,
        project_id: UUID,
        employee_id: UUID,
        labor_competencia: date,
        scenario: str | Scenario,
    ) -> int:
        """
        Reavalia snapshots COLLABORATOR do mês de pagamento (competência seguinte ao REALIZADO).

        Atualiza amount_original/amount_final em linhas abertas; preserva amount_paid e histórico.
        """
        if coerce_scenario(scenario) != Scenario.REALIZADO:
            return 0

        source_month = normalize_competencia(labor_competencia)
        payment_month = next_competencia(source_month)
        changed = 0

        real = await self._get_labor_row(
            project_id=project_id,
            employee_id=employee_id,
            competencia=source_month,
            scenario=Scenario.REALIZADO,
        )

        existing = list(
            (
                await self.session.execute(
                    select(PayableSnapshot).where(
                        PayableSnapshot.month == payment_month,
                        PayableSnapshot.type == PayableSnapshotType.COLLABORATOR,
                        PayableSnapshot.ref_id == employee_id,
                        PayableSnapshot.project_id == project_id,
                    )
                )
            )
            .scalars()
            .all()
        )

        if real is None or not real.employee or not real.project:
            removed = 0
            for row in existing:
                if _payable_row_is_dynamic_sync_protected(row):
                    continue
                if _money2(row.amount_paid) > 0:
                    continue
                await self.session.delete(row)
                removed += 1
                changed += 1
            if removed:
                logger.info(
                    "payables dynamic sync labor removed orphan rows project_id=%s employee_id=%s month=%s n=%d",
                    project_id,
                    employee_id,
                    payment_month,
                    removed,
                )
            await self.session.flush()
            return changed

        emp = real.employee
        proj = real.project
        settings = await SettingsService(self.session).get_or_create()
        factor = float(real.allocation_percentage or 0) / 100.0
        display_name = _employee_display_name(emp)
        cost_center = str(proj.name).strip()

        override_map = await self._payroll_override_map_for_month(
            employee_ids=[emp.id], source_month=source_month
        )
        integral_components = project_labor_payable_snapshot_components(
            emp, settings, source_month, real, payroll_override=override_map.get(emp.id)
        )
        allocated = _allocate_payable_components(integral_components, factor)
        expected: dict[str, Decimal] = {}
        for component_label, amt in allocated:
            snapshot_name = _collaborator_payable_snapshot_name(display_name, component_label)
            expected[snapshot_name] = Decimal(str(amt))

        consolidated = round(sum(float(v) for v in expected.values()), 2)
        logger.info(
            "payables dynamic sync labor start project_id=%s employee_id=%s source_month=%s payment_month=%s "
            "name=%s employment=%s allocation_pct=%s integral=%s expected=%s consolidated=%s",
            project_id,
            employee_id,
            source_month,
            payment_month,
            display_name,
            getattr(emp, "employment_type", None),
            real.allocation_percentage,
            [(lbl or "(único)", round(amt, 2)) for lbl, amt in integral_components],
            {k: float(v) for k, v in expected.items()},
            consolidated,
        )

        month_generated = await self.is_generated(month=payment_month)
        matched_ids: set[UUID] = set()

        for snapshot_name, new_amt in expected.items():
            row = next((r for r in existing if r.name == snapshot_name), None)
            if row is None:
                legacy = next(
                    (r for r in existing if r.name == display_name and r.id not in matched_ids),
                    None,
                )
                if legacy is not None:
                    row = legacy
                    row.name = snapshot_name
            if row is None:
                if new_amt <= 0 or not month_generated:
                    continue
                row = PayableSnapshot(
                    month=payment_month,
                    type=PayableSnapshotType.COLLABORATOR,
                    ref_id=emp.id,
                    project_id=proj.id,
                    name=snapshot_name,
                    cost_center=cost_center,
                    category="Mão de obra",
                    amount_original=new_amt,
                    amount_final=new_amt,
                    amount_paid=Decimal("0"),
                    due_date=_default_due_date(payment_month, day=10),
                    paid=False,
                    payment_date=None,
                    observation=None,
                )
                self.session.add(row)
                changed += 1
                _log_payable_dynamic_sync(
                    action="created",
                    row=row,
                    before_original=Decimal("0"),
                    before_final=Decimal("0"),
                    before_paid=Decimal("0"),
                )
                matched_ids.add(row.id)
                continue

            matched_ids.add(row.id)
            if _payable_row_is_dynamic_sync_protected(row):
                logger.info(
                    "payables dynamic sync skip protected snapshot_id=%s name=%s",
                    row.id,
                    row.name,
                )
                continue

            before_o = _money2(row.amount_original)
            before_f = _money2(row.amount_final)
            before_p = _money2(row.amount_paid)
            row.cost_center = cost_center
            _apply_dynamic_payable_amounts(row, new_amount=new_amt)
            changed += 1
            _log_payable_dynamic_sync(
                action="updated",
                row=row,
                before_original=before_o,
                before_final=before_f,
                before_paid=before_p,
            )

        for row in existing:
            if row.id in matched_ids:
                continue
            if _payable_row_is_dynamic_sync_protected(row):
                logger.info(
                    "payables dynamic sync skip protected orphan snapshot_id=%s name=%s",
                    row.id,
                    row.name,
                )
                continue
            if _money2(row.amount_paid) > 0:
                logger.info(
                    "payables dynamic sync preserve paid orphan snapshot_id=%s name=%s amount_paid=%s",
                    row.id,
                    row.name,
                    row.amount_paid,
                )
                continue
            logger.info(
                "payables dynamic sync remove orphan snapshot_id=%s name=%s",
                row.id,
                row.name,
            )
            await self.session.delete(row)
            changed += 1

        await self.session.flush()
        return changed

    async def _sync_project_cost_payable(
        self,
        *,
        source_kind: str,
        project_id: UUID,
        source_id: UUID,
        labor_competencia: date,
        scenario: str | Scenario,
        item_name: str | None = None,
        item_value: float | None = None,
    ) -> int:
        """
        Sincroniza custo diverso ou sistema no mesmo mês da competência do projeto (REALIZADO).

        Diferente da folha CLT: não usa mês seguinte. Com `item_name`/`item_value` None,
        remove snapshots automáticos abertos do `source_id`.
        """
        if coerce_scenario(scenario) != Scenario.REALIZADO:
            return 0

        payable_month = normalize_competencia(labor_competencia)
        is_misc = source_kind == "misc"
        category = CATEGORY_PROJECT_MISC if is_misc else CATEGORY_PROJECT_SYSTEM
        source_tag = SOURCE_TAG_PROJECT_MISC if is_misc else SOURCE_TAG_PROJECT_SYSTEM
        name_fallback = "Item" if is_misc else "Sistema"

        existing = list(
            (
                await self.session.execute(
                    select(PayableSnapshot).where(
                        PayableSnapshot.type == PayableSnapshotType.FIXED_COST,
                        PayableSnapshot.ref_id == source_id,
                        PayableSnapshot.project_id == project_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        row = next((r for r in existing if normalize_competencia(r.month) == payable_month), None)
        orphan_rows = [
            r
            for r in existing
            if normalize_competencia(r.month) != payable_month
            and _money2(r.amount_paid) <= 0
            and not _payable_row_is_dynamic_sync_protected(r)
        ]

        if item_name is None or item_value is None:
            removed = 0
            for r in existing:
                if _payable_row_is_dynamic_sync_protected(r):
                    continue
                if _money2(r.amount_paid) > 0:
                    continue
                await self.session.delete(r)
                removed += 1
            if removed:
                logger.info(
                    "payables dynamic sync %s removed project_id=%s source_id=%s n=%d",
                    source_kind,
                    project_id,
                    source_id,
                    removed,
                )
            await self.session.flush()
            return removed

        amount = float(item_value or 0.0)
        proj = await self.session.get(Project, project_id)
        if not proj or getattr(proj, "deleted_at", None) is not None:
            return 0
        cost_center = _project_cost_center_label(proj)
        snapshot_name = _project_item_snapshot_name(item_name, fallback=name_fallback)
        new_amt = Decimal(str(round(amount, 2)))
        due = _default_due_date(payable_month, day=10)

        if amount <= 0:
            return await self._sync_project_cost_payable(
                source_kind=source_kind,
                project_id=project_id,
                source_id=source_id,
                labor_competencia=labor_competencia,
                scenario=scenario,
                item_name=None,
                item_value=None,
            )

        month_generated = await self.is_generated(month=payable_month)
        changed = 0

        if row is None and orphan_rows:
            row = orphan_rows[0]
            row.month = payable_month
            row.due_date = due

        if row is None:
            if not month_generated:
                await self.session.flush()
                return 0
            row = PayableSnapshot(
                month=payable_month,
                type=PayableSnapshotType.FIXED_COST,
                ref_id=source_id,
                project_id=project_id,
                name=snapshot_name,
                cost_center=cost_center,
                category=category,
                amount_original=new_amt,
                amount_final=new_amt,
                amount_paid=Decimal("0"),
                due_date=due,
                paid=False,
                payment_date=None,
                observation=source_tag,
            )
            self.session.add(row)
            changed += 1
            _log_payable_dynamic_sync(
                action=f"created_{source_kind}",
                row=row,
                before_original=Decimal("0"),
                before_final=Decimal("0"),
                before_paid=Decimal("0"),
            )
        else:
            if _payable_row_is_dynamic_sync_protected(row):
                logger.info(
                    "payables dynamic sync skip protected %s snapshot_id=%s",
                    source_kind,
                    row.id,
                )
            else:
                before_o = _money2(row.amount_original)
                before_f = _money2(row.amount_final)
                before_p = _money2(row.amount_paid)
                row.month = payable_month
                row.due_date = due
                row.name = snapshot_name
                row.cost_center = cost_center
                row.category = category
                if not (row.observation or "").strip():
                    row.observation = source_tag
                _apply_dynamic_payable_amounts(row, new_amount=new_amt)
                changed += 1
                _log_payable_dynamic_sync(
                    action=f"updated_{source_kind}",
                    row=row,
                    before_original=before_o,
                    before_final=before_f,
                    before_paid=before_p,
                )

        if row is not None:
            for orphan in orphan_rows:
                if orphan.id == row.id:
                    continue
                await self.session.delete(orphan)
                changed += 1

        await self.session.flush()
        return changed

    async def sync_project_misc_cost_payables(
        self,
        *,
        project_id: UUID,
        cost_id: UUID,
        labor_competencia: date,
        scenario: str | Scenario,
    ) -> int:
        row = await self.session.get(ProjectOperationalFixed, cost_id)
        if row is None or row.project_id != project_id:
            return await self._sync_project_cost_payable(
                source_kind="misc",
                project_id=project_id,
                source_id=cost_id,
                labor_competencia=labor_competencia,
                scenario=scenario,
                item_name=None,
                item_value=None,
            )
        return await self._sync_project_cost_payable(
            source_kind="misc",
            project_id=project_id,
            source_id=cost_id,
            labor_competencia=normalize_competencia(row.competencia),
            scenario=scenario,
            item_name=row.name,
            item_value=float(row.value or 0),
        )

    async def sync_project_system_payables(
        self,
        *,
        project_id: UUID,
        system_id: UUID,
        labor_competencia: date,
        scenario: str | Scenario,
    ) -> int:
        row = await self.session.get(ProjectSystemCost, system_id)
        if row is None or row.project_id != project_id:
            return await self._sync_project_cost_payable(
                source_kind="system",
                project_id=project_id,
                source_id=system_id,
                labor_competencia=labor_competencia,
                scenario=scenario,
                item_name=None,
                item_value=None,
            )
        return await self._sync_project_cost_payable(
            source_kind="system",
            project_id=project_id,
            source_id=system_id,
            labor_competencia=normalize_competencia(row.competencia),
            scenario=scenario,
            item_name=row.name,
            item_value=float(row.value or 0),
        )

    async def sync_collaborator_payables_for_employee(self, *, employee_id: UUID) -> int:
        """Reavalia snapshots de todos os vínculos REALIZADO do colaborador."""
        keys = (
            await self.session.execute(
                select(ProjectLabor.project_id, ProjectLabor.competencia)
                .where(
                    ProjectLabor.employee_id == employee_id,
                    ProjectLabor.scenario == scenario_pg_rhs(Scenario.REALIZADO),
                )
                .distinct()
            )
        ).all()
        total = 0
        for project_id, comp in keys:
            total += await self.sync_collaborator_payables_for_labor(
                project_id=project_id,
                employee_id=employee_id,
                labor_competencia=comp,
                scenario=Scenario.REALIZADO,
            )
        return total

    async def preserve_or_remove_deleted_company_finance_item(self, *, item_id: UUID) -> int:
        """
        Remove snapshots corporativos órfãos de um item excluído, mas preserva qualquer linha
        que já tenha pagamento registrado para manter o histórico financeiro.
        """
        rows = (
            await self.session.execute(
                select(PayableSnapshot).where(
                    PayableSnapshot.ref_id == item_id,
                    PayableSnapshot.type.in_((PayableSnapshotType.FIXED_COST, *PAYABLE_DEBT_TYPES)),
                )
            )
        ).scalars().all()
        removed = 0
        for row in rows:
            if _money2(row.amount_paid) > 0:
                _sync_legacy_paid_fields(row)
                continue
            await self.session.delete(row)
            removed += 1
        await self.session.flush()
        return removed

    async def _ensure_invoice_anticipation_obligations(
        self,
        *,
        payment_month: date,
        project_ids: set[UUID] | None,
    ) -> int:
        """
        Backfill seguro: garante que antecipações de NFs criem obrigações no snapshot do mês,
        mesmo que o mês já tenha sido "congelado" anteriormente.
        """
        comp = normalize_competencia(payment_month)
        start, end = _month_bounds(comp)

        existing_ref_ids = set(
            (
                await self.session.execute(
                    select(PayableSnapshot.ref_id).where(
                        PayableSnapshot.month == comp,
                        PayableSnapshot.type == PayableSnapshotType.ANTECIPACAO,
                        PayableSnapshot.ref_id.is_not(None),
                    )
                )
            )
            .scalars()
            .all()
        )

        ant_stmt = (
            select(ReceivableInvoiceAnticipation, ReceivableInvoice)
            .join(ReceivableInvoice, ReceivableInvoice.id == ReceivableInvoiceAnticipation.invoice_id)
            .where(
                ReceivableInvoiceAnticipation.amount_to_repay > 0,
                ReceivableInvoice.invoice_status != "CANCELADA",
                (
                    (ReceivableInvoice.received_date >= start) & (ReceivableInvoice.received_date <= end)
                )
                | (
                    (ReceivableInvoiceAnticipation.due_date >= start)
                    & (ReceivableInvoiceAnticipation.due_date <= end)
                ),
            )
        )
        if project_ids is not None:
            ant_stmt = ant_stmt.where(ReceivableInvoice.project_id.in_(sorted(project_ids)))

        rows = (await self.session.execute(ant_stmt)).all()
        created = 0
        for ant, inv in rows:
            if ant.id in existing_ref_ids:
                continue
            amt = float(ant.amount_to_repay or 0.0)
            if amt <= 0:
                continue
            obligation_date = inv.received_date or ant.due_date
            if obligation_date is None:
                continue
            if not (start <= obligation_date <= end):
                continue
            inst = str(ant.institution or "").strip() or "Instituição"
            name = f"NF {str(inv.nf_number).strip()} - {inst}"
            self.session.add(
                PayableSnapshot(
                    month=comp,
                    type=PayableSnapshotType.ANTECIPACAO,
                    ref_id=ant.id,
                    project_id=inv.project_id,
                    name=name,
                    cost_center="Financeiro",
                    category="Antecipações",
                    amount_original=Decimal(str(round(amt, 2))),
                    amount_final=Decimal(str(round(amt, 2))),
                    amount_paid=Decimal("0"),
                    due_date=obligation_date,
                    paid=False,
                    payment_date=None,
                    observation=None,
                )
            )
            created += 1

        if created:
            logger.warning(
                "payables invoice anticipation backfill applied month=%s added=%d",
                comp,
                created,
            )
        return created

    async def _has_stale_invoice_anticipation_rows(self, *, month: date) -> bool:
        """
        Detecta 'fantasmas': linhas ANTECIPACAO no snapshot cujo ref_id não existe mais
        em `receivable_invoice_anticipations` (ex.: NF/antecipação foi excluída e o mês não foi invalidado).
        """
        comp = normalize_competencia(month)
        stmt = (
            select(func.count())
            .select_from(PayableSnapshot)
            .where(
                PayableSnapshot.month == comp,
                PayableSnapshot.type == PayableSnapshotType.ANTECIPACAO,
                PayableSnapshot.ref_id.is_not(None),
                ~PayableSnapshot.ref_id.in_(select(ReceivableInvoiceAnticipation.id)),
            )
        )
        return int((await self.session.execute(stmt)).scalar_one() or 0) > 0

    async def get_or_create_for_month(
        self,
        *,
        payment_month: date,
        accessible_project_ids: set[UUID] | None,
        sees_all_projects: bool,
        force_regenerate: bool = False,
    ) -> list[PayableSnapshot]:
        """
        Snapshot imutável: após marcado em `payable_snapshot_generations`, não recalcula.

        Observação: a geração é serializada por mês via `pg_advisory_xact_lock` para evitar duplicação sob concorrência.
        """
        comp = normalize_competencia(payment_month)
        source_month = previous_competencia(comp)
        project_count = 0 if not accessible_project_ids else len(accessible_project_ids)

        logger.info(
            "payables get_or_create_for_month start month=%s source_month=%s sees_all=%s accessible_projects=%d force=%s",
            comp,
            source_month,
            sees_all_projects,
            project_count,
            force_regenerate,
        )

        try:
            if await self.is_generated(month=comp) and not force_regenerate:
                existing = await self.list_for_month(month=comp)
                if len(existing) == 0:
                    logger.error(
                        "payables snapshot month=%s is marked generated but has 0 rows; "
                        "refusing auto-regeneration (audit required). sees_all=%s accessible_projects=%d",
                        comp,
                        sees_all_projects,
                        project_count,
                    )
                    return []
                else:
                    # Não recria snapshots gerados automaticamente aqui: isso apaga histórico financeiro
                    # (amount_paid) de linhas automáticas. Inconsistências devem ser corrigidas de forma
                    # pontual ou por regeneração explícita e auditável.
                    if await self._has_stale_invoice_anticipation_rows(month=comp):
                        logger.error("payables snapshot month=%s has stale ANTECIPACAO rows; preserving snapshot.", comp)
                    if existing and not force_regenerate:
                        added_fixed = await self._ensure_company_finance_manual_entries(payment_month=comp)
                        added_ants = await self._ensure_invoice_anticipation_obligations(
                            payment_month=comp,
                            project_ids=None if sees_all_projects else (accessible_project_ids or None),
                        )
                        if added_fixed or added_ants:
                            await self.session.flush()
                            return await self.list_for_month(month=comp)
                        return existing

            lock_key = int(comp.strftime("%Y%m"))
            await self.session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": lock_key})

            if await self.is_generated(month=comp) and not force_regenerate:
                existing = await self.list_for_month(month=comp)
                if len(existing) > 0:
                    if await self._has_stale_invoice_anticipation_rows(month=comp):
                        logger.error(
                            "payables snapshot month=%s has stale ANTECIPACAO rows (under lock); preserving snapshot.",
                            comp,
                        )
                    if existing and not force_regenerate:
                        added_fixed = await self._ensure_company_finance_manual_entries(payment_month=comp)
                        added_ants = await self._ensure_invoice_anticipation_obligations(
                            payment_month=comp,
                            project_ids=None if sees_all_projects else (accessible_project_ids or None),
                        )
                        if added_fixed or added_ants:
                            await self.session.flush()
                            return await self.list_for_month(month=comp)
                        return existing
                logger.error(
                    "payables snapshot month=%s has generation marker but 0 rows under lock; "
                    "refusing auto-regeneration. sees_all=%s accessible_projects=%d",
                    comp,
                    sees_all_projects,
                    project_count,
                )
                return []

            if force_regenerate:
                paid_rows = await self._count_paid_automatic_rows(month=comp)
                if paid_rows > 0:
                    raise ValueError(
                        f"Snapshot de {comp:%Y-%m} possui {paid_rows} lançamento(s) automático(s) pago(s); "
                        "regeração bloqueada para preservar o histórico financeiro."
                    )
                # Regeneração explícita: remove linhas automáticas + marcador. MANUAL preservado (como em invalidate).
                logger.warning("force_regenerate payables snapshot month=%s source_month=%s", comp, source_month)
                await self.session.execute(
                    delete(PayableSnapshot).where(
                        PayableSnapshot.month == comp,
                        PayableSnapshot.type != PayableSnapshotType.MANUAL,
                    )
                )
                await self.session.execute(
                    text("DELETE FROM payable_snapshot_generations WHERE month = :m"),
                    {"m": comp},
                )
                await self.session.flush()

            # Compat legado: já há linhas geradas automaticamente e snapshot sem marcador → só congela.
            # Se só restarem linhas MANUAIS (invalidação preservou despesa avulsa), segue e regera o restante.
            if (await self.count_for_month(month=comp) > 0) and (not force_regenerate):
                non_manual = int(
                    (
                        await self.session.scalar(
                            select(func.count())
                            .select_from(PayableSnapshot)
                            .where(
                                PayableSnapshot.month == comp,
                                PayableSnapshot.type != PayableSnapshotType.MANUAL,
                            )
                        )
                    )
                    or 0
                )
                if non_manual > 0:
                    if not await self.is_generated(month=comp):
                        now = datetime.now(timezone.utc)
                        self.session.add(PayableSnapshotGeneration(month=comp, created_at=now))
                        await self.session.flush()
                    return await self.list_for_month(month=comp)

            created = await self._generate_snapshot(
                payment_month=comp,
                accessible_project_ids=accessible_project_ids,
                sees_all_projects=sees_all_projects,
            )
            await self.session.flush()

            logger.info(
                "generated payables snapshot month=%s source_month=%s sees_all=%s accessible_projects=%d rows=%d",
                comp,
                source_month,
                sees_all_projects,
                project_count,
                created,
            )

            if created <= 0:
                # Mês só com despesas manuais preservadas: ainda assim congela se houver linhas.
                if (await self.count_for_month(month=comp)) <= 0:
                    raise ValueError(
                        f"Snapshot não gerado para {comp:%Y-%m}: nenhuma linha foi criada "
                        f"(sees_all={sees_all_projects}, accessible_projects={project_count})."
                    )

            # Proteção: se algum marker existir (estado inconsistente), substitui.
            await self.session.execute(
                text("DELETE FROM payable_snapshot_generations WHERE month = :m"),
                {"m": comp},
            )
            now = datetime.now(timezone.utc)
            self.session.add(PayableSnapshotGeneration(month=comp, created_at=now))
            await self.session.flush()
            return await self.list_for_month(month=comp)
        except Exception as e:  # noqa: BLE001
            logger.exception(
                "payables get_or_create_for_month failed month=%s source_month=%s sees_all=%s accessible_projects=%d force=%s error=%s",
                comp,
                source_month,
                sees_all_projects,
                project_count,
                force_regenerate,
                str(e),
            )
            raise

    async def _generate_snapshot(
        self,
        *,
        payment_month: date,
        accessible_project_ids: set[UUID] | None,
        sees_all_projects: bool,
    ) -> int:
        source_month = previous_competencia(payment_month)
        try:
            settings = await SettingsService(self.session).get_or_create()
            due = _default_due_date(payment_month, day=10)

            project_filter: set[UUID] | None = None
            if not sees_all_projects:
                if not accessible_project_ids:
                    # Financeiro não deve depender de project_users. Fallback para todos os projetos.
                    all_ids = await ProjectRepository(self.session).list_all_project_ids()
                    logger.warning(
                        "Fallback para todos projetos aplicado (payables). month=%s source_month=%s "
                        "original_accessible_count=0 final_accessible_count=%d",
                        payment_month,
                        source_month,
                        len(all_ids),
                    )
                    accessible_project_ids = set(all_ids)
                project_filter = set(accessible_project_ids)

            created = 0

            # --- Collaborators (individual; somente REALIZADO) ---
            keys_stmt = select(ProjectLabor.project_id, ProjectLabor.employee_id).where(
                ProjectLabor.competencia == source_month,
                ProjectLabor.scenario == scenario_pg_rhs(Scenario.REALIZADO),
                ProjectLabor.employee_id.is_not(None),
            )
            if project_filter is not None:
                keys_stmt = keys_stmt.where(ProjectLabor.project_id.in_(sorted(project_filter)))
            keys_stmt = keys_stmt.distinct()
            keys = (await self.session.execute(keys_stmt)).all()
            employee_ids = list({employee_id for _, employee_id in keys})
            payroll_override_map = await self._payroll_override_map_for_month(
                employee_ids=employee_ids, source_month=source_month
            )

            for project_id, employee_id in keys:
                real = await self._get_labor_row(
                    project_id=project_id,
                    employee_id=employee_id,
                    competencia=source_month,
                    scenario=Scenario.REALIZADO,
                )
                if real is None:
                    continue

                emp = real.employee
                proj = real.project
                if not emp or not proj:
                    continue

                factor = float(real.allocation_percentage or 0) / 100.0
                if factor <= 0:
                    continue

                display_name = _employee_display_name(emp)
                integral_components = project_labor_payable_snapshot_components(
                    emp,
                    settings,
                    source_month,
                    real,
                    payroll_override=payroll_override_map.get(emp.id),
                )
                allocated = _allocate_payable_components(integral_components, factor)
                if not allocated:
                    continue

                consolidated = round(sum(amt for _, amt in allocated), 2)
                employment = (getattr(emp, "employment_type", "") or "").strip().upper()
                logger.info(
                    "payables collaborator snapshot employee_id=%s project_id=%s name=%s "
                    "employment=%s allocation_pct=%s integral_components=%s allocated=%s consolidated=%s",
                    emp.id,
                    proj.id,
                    display_name,
                    employment,
                    real.allocation_percentage,
                    [(lbl or "(único)", round(amt, 2)) for lbl, amt in integral_components],
                    [(lbl or "(único)", amt) for lbl, amt in allocated],
                    consolidated,
                )

                for component_label, amount in allocated:
                    snapshot_name = _collaborator_payable_snapshot_name(display_name, component_label)
                    self.session.add(
                        PayableSnapshot(
                            month=payment_month,
                            type=PayableSnapshotType.COLLABORATOR,
                            ref_id=emp.id,
                            project_id=proj.id,
                            name=snapshot_name,
                            cost_center=str(proj.name).strip(),
                            category="Mão de obra",
                            amount_original=Decimal(str(amount)),
                            amount_final=Decimal(str(amount)),
                            amount_paid=Decimal("0"),
                            due_date=due,
                            paid=False,
                            payment_date=None,
                            observation=None,
                        )
                    )
                    created += 1
                    logger.info(
                        "payables collaborator line employee_id=%s project_id=%s name=%s amount=%s",
                        emp.id,
                        proj.id,
                        snapshot_name,
                        amount,
                    )

            # --- Vehicles (aggregated) ---
            # Regra nova: distribuir por projeto (centro de custo real) — nunca usar "Operacional".
            vehicle_by_project = await self._sum_vehicle_monthly_cost_by_project(
                competencia=source_month,
                project_ids=project_filter,
            )
            for project_id, project_name, total in vehicle_by_project:
                amount = float(total or 0.0)
                if amount <= 0:
                    continue
                self.session.add(
                    PayableSnapshot(
                        month=payment_month,
                        type=PayableSnapshotType.VEHICLE,
                        ref_id=None,
                        project_id=project_id,
                        name="Custo com veículos",
                        cost_center=project_name,
                        category="Combustível / veículos",
                        amount_original=Decimal(str(round(amount, 2))),
                        amount_final=Decimal(str(round(amount, 2))),
                        amount_paid=Decimal("0"),
                        due_date=due,
                        paid=False,
                        payment_date=None,
                        observation=None,
                    )
                )
                created += 1

            # --- Company finance (manual entries only): custos diversos + endividamento ---
            # Regra nova: NÃO gerar automaticamente pelo valor de referência.
            # Só entra no contas a pagar se houver valor lançado manualmente no mês (company_financial_payments).
            payments_rows = (
                await self.session.execute(
                    select(CompanyFinancialPayment, CompanyFinancialItem)
                    .join(CompanyFinancialItem, CompanyFinancialItem.id == CompanyFinancialPayment.item_id)
                    .where(
                        CompanyFinancialPayment.competencia == payment_month,
                        CompanyFinancialPayment.valor > 0,
                        CompanyFinancialItem.tipo.in_(("custo_fixo", "endividamento")),
                    )
                )
            ).all()
            for p, it in payments_rows:
                amt = float(p.valor or 0.0)
                if amt <= 0:
                    continue
                snap_type, cost_center, category = await self._company_finance_snapshot_meta(it)
                self.session.add(
                    PayableSnapshot(
                        month=payment_month,
                        type=snap_type,
                        ref_id=it.id,
                        project_id=None,
                        name=str(it.nome).strip(),
                        cost_center=cost_center,
                        category=category,
                        amount_original=Decimal(str(round(amt, 2))),
                        amount_final=Decimal(str(round(amt, 2))),
                        amount_paid=Decimal("0"),
                        due_date=due,
                        paid=False,
                        payment_date=None,
                        observation=None,
                    )
                )
                created += 1

            # --- Custos diversos (operacional) — um snapshot por item ---
            misc_stmt = (
                select(ProjectOperationalFixed)
                .options(selectinload(ProjectOperationalFixed.project))
                .where(
                    ProjectOperationalFixed.competencia == source_month,
                    ProjectOperationalFixed.scenario == scenario_pg_rhs(Scenario.REALIZADO),
                )
            )
            if project_filter is not None:
                misc_stmt = misc_stmt.where(ProjectOperationalFixed.project_id.in_(sorted(project_filter)))
            for misc_row in (await self.session.execute(misc_stmt)).scalars().all():
                amt = float(misc_row.value or 0.0)
                if amt <= 0 or not misc_row.project:
                    continue
                if getattr(misc_row.project, "deleted_at", None) is not None:
                    continue
                self.session.add(
                    PayableSnapshot(
                        month=payment_month,
                        type=PayableSnapshotType.FIXED_COST,
                        ref_id=misc_row.id,
                        project_id=misc_row.project_id,
                        name=_project_item_snapshot_name(misc_row.name),
                        cost_center=_project_cost_center_label(misc_row.project),
                        category=CATEGORY_PROJECT_MISC,
                        amount_original=Decimal(str(round(amt, 2))),
                        amount_final=Decimal(str(round(amt, 2))),
                        amount_paid=Decimal("0"),
                        due_date=_default_due_date(payment_month, day=10),
                        paid=False,
                        payment_date=None,
                        observation=SOURCE_TAG_PROJECT_MISC,
                    )
                )
                created += 1

            # --- Sistemas do projeto — um snapshot por item ---
            sys_stmt = (
                select(ProjectSystemCost)
                .options(selectinload(ProjectSystemCost.project))
                .where(
                    ProjectSystemCost.competencia == source_month,
                    ProjectSystemCost.scenario == scenario_pg_rhs(Scenario.REALIZADO),
                )
            )
            if project_filter is not None:
                sys_stmt = sys_stmt.where(ProjectSystemCost.project_id.in_(sorted(project_filter)))
            for sys_row in (await self.session.execute(sys_stmt)).scalars().all():
                amt = float(sys_row.value or 0.0)
                if amt <= 0 or not sys_row.project:
                    continue
                if getattr(sys_row.project, "deleted_at", None) is not None:
                    continue
                self.session.add(
                    PayableSnapshot(
                        month=payment_month,
                        type=PayableSnapshotType.FIXED_COST,
                        ref_id=sys_row.id,
                        project_id=sys_row.project_id,
                        name=_project_item_snapshot_name(sys_row.name, fallback="Sistema"),
                        cost_center=_project_cost_center_label(sys_row.project),
                        category=CATEGORY_PROJECT_SYSTEM,
                        amount_original=Decimal(str(round(amt, 2))),
                        amount_final=Decimal(str(round(amt, 2))),
                        amount_paid=Decimal("0"),
                        due_date=_default_due_date(payment_month, day=10),
                        paid=False,
                        payment_date=None,
                        observation=SOURCE_TAG_PROJECT_SYSTEM,
                    )
                )
                created += 1

            # --- Custos diversos legado (agregado por nome, sem ref_id) ---
            fixed_rows = await self._project_fixed_cost_legacy_rows(
                competencia=source_month, project_ids=project_filter
            )
            for project_id, display_name, amount, cost_center_label, category in fixed_rows:
                amount = float(amount or 0.0)
                if amount <= 0:
                    continue
                self.session.add(
                    PayableSnapshot(
                        month=payment_month,
                        type=PayableSnapshotType.FIXED_COST,
                        ref_id=None,
                        project_id=project_id,
                        name=display_name,
                        cost_center=cost_center_label,
                        category=category,
                        amount_original=Decimal(str(round(amount, 2))),
                        amount_final=Decimal(str(round(amount, 2))),
                        amount_paid=Decimal("0"),
                        due_date=due,
                        paid=False,
                        payment_date=None,
                        observation=None,
                    )
                )
                created += 1

            # --- Anticipated invoices: future obligation (return of advance) ---
            # Regra: TODA antecipação gera uma obrigação futura (não depende do status/pagamento da NF).
            # Vencimento da obrigação:
            # - se a NF tiver `received_date`, a obrigação nasce no recebimento (ignora due_date da antecipação)
            # - caso contrário, usa `due_date` da antecipação
            start, end = _month_bounds(payment_month)
            ant_stmt = (
                select(ReceivableInvoiceAnticipation, ReceivableInvoice)
                .join(ReceivableInvoice, ReceivableInvoice.id == ReceivableInvoiceAnticipation.invoice_id)
                .where(
                    ReceivableInvoiceAnticipation.amount_to_repay > 0,
                    ReceivableInvoice.invoice_status != "CANCELADA",
                    # Busca "candidatos" do mês: por devolução OU por recebimento.
                    # O filtro final por mês é feito via obligation_date abaixo.
                    (
                        (ReceivableInvoice.received_date >= start) & (ReceivableInvoice.received_date <= end)
                    )
                    | (
                        (ReceivableInvoiceAnticipation.due_date >= start) & (ReceivableInvoiceAnticipation.due_date <= end)
                    ),
                )
            )
            if project_filter is not None:
                ant_stmt = ant_stmt.where(ReceivableInvoice.project_id.in_(sorted(project_filter)))

            ants = (await self.session.execute(ant_stmt)).all()
            for ant, inv in ants:
                amt = float(ant.amount_to_repay or 0.0)
                if amt <= 0:
                    continue
                obligation_date = inv.received_date or ant.due_date
                if obligation_date is None:
                    continue
                if not (start <= obligation_date <= end):
                    continue
                inst = str(ant.institution or "").strip() or "Instituição"
                name = f"NF {str(inv.nf_number).strip()} - {inst}"
                self.session.add(
                    PayableSnapshot(
                        month=payment_month,
                        type=PayableSnapshotType.ANTECIPACAO,
                        ref_id=ant.id,
                        project_id=inv.project_id,
                        name=name,
                        cost_center="Financeiro",
                        category="Antecipações",
                        amount_original=Decimal(str(round(amt, 2))),
                        amount_final=Decimal(str(round(amt, 2))),
                        amount_paid=Decimal("0"),
                        due_date=obligation_date,
                        paid=False,
                        payment_date=None,
                        observation=None,
                    )
                )
                created += 1

            logger.info(
                "payables _generate_snapshot month=%s source_month=%s sees_all=%s accessible_projects=%s labor_keys=%d "
                "vehicle_total=%.2f fixed_items=%d created=%d",
                payment_month,
                source_month,
                sees_all_projects,
                "ALL" if sees_all_projects else (len(project_filter) if project_filter is not None else 0),
                len(keys),
                float(sum(v for _, __, v in vehicle_by_project)),
                len(fixed_rows),
                created,
            )

            return created
        except Exception as e:  # noqa: BLE001
            logger.exception(
                "payables _generate_snapshot failed month=%s source_month=%s sees_all=%s accessible_projects=%s error=%s",
                payment_month,
                source_month,
                sees_all_projects,
                "ALL" if sees_all_projects else (len(accessible_project_ids) if accessible_project_ids else 0),
                str(e),
            )
            raise

    async def _get_labor_row(
        self, *, project_id: UUID, employee_id: UUID, competencia: date, scenario: Scenario
    ) -> ProjectLabor | None:
        stmt = (
            select(ProjectLabor)
            .options(selectinload(ProjectLabor.employee), selectinload(ProjectLabor.project))
            .where(
                ProjectLabor.project_id == project_id,
                ProjectLabor.employee_id == employee_id,
                ProjectLabor.competencia == competencia,
                ProjectLabor.scenario == scenario_pg_rhs(scenario),
            )
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _sum_vehicle_monthly_cost(self, *, competencia: date, project_ids: set[UUID] | None) -> float:
        stmt = select(func.coalesce(func.sum(ProjectVehicle.monthly_cost), 0)).where(
            ProjectVehicle.competencia == competencia,
            ProjectVehicle.scenario == scenario_pg_rhs(Scenario.REALIZADO),
        )
        if project_ids is not None:
            stmt = stmt.where(ProjectVehicle.project_id.in_(sorted(project_ids)))
        return float((await self.session.execute(stmt)).scalar_one())

    async def _sum_vehicle_monthly_cost_by_project(
        self,
        *,
        competencia: date,
        project_ids: set[UUID] | None,
    ) -> list[tuple[UUID, str, float]]:
        """
        Soma custo mensal de veículos por projeto na competência.

        Regra (caixa real): considerar SOMENTE valores informados no mês (REALIZADO).
        Retorna lista (project_id, project_name, total_cost).
        """
        stmt = (
            select(
                ProjectVehicle.project_id,
                func.coalesce(func.sum(ProjectVehicle.monthly_cost), 0),
            )
            .where(
                ProjectVehicle.competencia == competencia,
                ProjectVehicle.scenario == scenario_pg_rhs(Scenario.REALIZADO),
                ProjectVehicle.monthly_cost.is_not(None),
                ProjectVehicle.monthly_cost > 0,
            )
            .group_by(ProjectVehicle.project_id)
        )
        if project_ids is not None:
            stmt = stmt.where(ProjectVehicle.project_id.in_(sorted(project_ids)))
        pairs = (await self.session.execute(stmt)).all()
        if not pairs:
            return []
        ids = [pid for pid, _ in pairs]
        projects = (await self.session.execute(select(Project).where(Project.id.in_(ids)))).scalars().all()
        name_map = {p.id: str(p.name).strip() for p in projects}
        out: list[tuple[UUID, str, float]] = []
        for pid, total in pairs:
            out.append((pid, name_map.get(pid, str(pid)), float(total or 0.0)))
        return out

    async def _project_fixed_cost_legacy_rows(
        self, *, competencia: date, project_ids: set[UUID] | None
    ) -> list[tuple[UUID, str, float, str, str]]:
        """
        Custos diversos legados (`project_fixed_costs`), agregados por projeto × nome.

        Retorna tuplas: (project_id, name, amount, cost_center_label, category)
        """
        leg_real: dict[tuple[UUID, str], float] = defaultdict(float)
        stmt = (
            select(ProjectFixedCost.project_id, ProjectFixedCost.name, func.sum(ProjectFixedCost.amount_real))
            .where(
                ProjectFixedCost.competencia == competencia,
                ProjectFixedCost.scenario == scenario_pg_rhs(Scenario.REALIZADO),
            )
        )
        if project_ids is not None:
            stmt = stmt.where(ProjectFixedCost.project_id.in_(sorted(project_ids)))
        stmt = stmt.group_by(ProjectFixedCost.project_id, ProjectFixedCost.name)
        for pid, name, total in (await self.session.execute(stmt)).all():
            base = str(name).strip()
            if not base:
                continue
            leg_real[(pid, base)] += float(total or 0.0)

        if not leg_real:
            return []

        proj_ids = {pid for pid, _ in leg_real}
        projects = (await self.session.execute(select(Project).where(Project.id.in_(sorted(proj_ids))))).scalars().all()
        proj_map = {p.id: p for p in projects}

        rows: list[tuple[UUID, str, float, str, str]] = []
        for pid, base in sorted(leg_real.keys(), key=lambda t: (str(t[0]), t[1])):
            amount = float(leg_real.get((pid, base), 0.0) or 0.0)
            if amount <= 0:
                continue

            proj = proj_map.get(pid)
            if proj is None or getattr(proj, "deleted_at", None) is not None:
                continue

            cc = _project_cost_center_label(proj)
            rows.append((pid, base, amount, cc, "Custos diversos (legado)"))

        return rows

    async def _validate_manual_cost_center(self, cost_center: str) -> str:
        cc = " ".join(str(cost_center).strip().split())
        if not cc:
            raise ValueError("Centro de custo é obrigatório.")
        lowered = cc.casefold()
        for fixed in MANUAL_PAYABLE_FIXED_COST_CENTERS:
            if fixed.casefold() == lowered:
                return fixed
        exact = (
            await self.session.execute(
                select(Project.name).where(Project.deleted_at.is_(None), Project.name == cc).limit(1)
            )
        ).scalar_one_or_none()
        if exact:
            return str(exact)
        insensitive = (
            await self.session.execute(
                select(Project.name).where(
                    Project.deleted_at.is_(None),
                    func.lower(Project.name) == lowered,
                ).limit(1)
            )
        ).scalar_one_or_none()
        if insensitive:
            return str(insensitive)
        raise ValueError(
            "Centro de custo inválido. Use «Administrativo», «Financeiro» ou o nome exato de um projeto cadastrado."
        )

    async def create_manual(
        self,
        *,
        month: date,
        name: str,
        category: str,
        cost_center: str,
        amount: float,
        due_date: date,
        observation: str | None = None,
        snapshot_type: PayableSnapshotType = PayableSnapshotType.MANUAL,
    ) -> PayableSnapshot:
        # Manual: competência = mês do vencimento (obrigação), não o mês do filtro da tela.
        comp = normalize_competencia(due_date)
        amt = Decimal(str(round(float(amount), 2)))
        cc = await self._validate_manual_cost_center(cost_center)
        obs = (observation or "").strip() or None
        row = PayableSnapshot(
            month=comp,
            type=snapshot_type,
            ref_id=uuid4(),
            project_id=None,
            name=str(name).strip(),
            cost_center=cc,
            category=str(category).strip(),
            amount_original=amt,
            amount_final=amt,
            amount_paid=Decimal("0"),
            due_date=due_date,
            paid=False,
            payment_date=None,
            observation=obs,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def update_row(self, *, row: PayableSnapshot, amount_final: float | None, due_date: date | None, observation: str | None) -> PayableSnapshot:
        if amount_final is not None:
            row.amount_final = Decimal(str(round(float(amount_final), 2)))
            self._append_observation(row, PAYABLE_MANUAL_ADJUSTMENT_TAG)
        if due_date is not None:
            row.due_date = due_date
        if observation is not None:
            row.observation = observation
        await self.session.flush()
        await self._recalculate_amount_paid(row)
        if amount_final is not None:
            af = _money2(row.amount_final)
            cur_paid = _money2(row.amount_paid)
            if cur_paid > af + PAYABLE_PAYMENT_TOLERANCE:
                excess = (cur_paid - af).quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)
                await self.reverse_payment(
                    row=row,
                    amount=float(excess),
                    reversal_reason="Ajuste automático por redução do valor final.",
                )
        await self.session.flush()
        return row

    def _append_observation(self, row: PayableSnapshot, line: str) -> None:
        line = line.strip()
        if not line:
            return
        prev = (row.observation or "").strip()
        row.observation = f"{prev}\n{line}".strip() if prev else line

    async def register_payment(
        self,
        *,
        row: PayableSnapshot,
        amount: float,
        payment_date: date | None = None,
        observation: str | None = None,
        created_by: UUID | None = None,
        allow_overpayment: bool = False,
    ) -> PayableSnapshot:
        amt = _money2(amount)
        if amt <= 0:
            raise ValueError("Valor do pagamento deve ser maior que zero.")
        if amt > Decimal("999999999.99"):
            raise ValueError("Valor do pagamento fora do limite permitido.")

        pd = _validate_payment_date(payment_date)
        final = _money2(row.amount_final)
        paid_cur = await self._sum_active_payments(row.id)
        remaining = _payable_remaining_balance(amount_final=final, amount_paid=paid_cur)

        if not allow_overpayment and remaining > PAYABLE_PAYMENT_TOLERANCE and amt > remaining + PAYABLE_PAYMENT_TOLERANCE:
            raise ValueError(
                f"Valor excede o saldo em aberto ({remaining}). "
                "Confirme pagamento acima do saldo ou ajuste o valor."
            )

        before_derived = payable_snapshot_derived_fields(amount_paid=paid_cur, amount_final=final)
        logger.info(
            "payables register_payment before snapshot_id=%s name=%s amount_final=%s amount_paid=%s "
            "saldo=%s status=%s payment=%s payment_date=%s",
            row.id,
            row.name,
            final,
            paid_cur,
            before_derived["amount_remaining"],
            before_derived["status"],
            amt,
            pd,
        )

        self.session.add(
            PayablePayment(
                payable_snapshot_id=row.id,
                amount=amt,
                payment_date=pd,
                observation=(observation or "").strip() or None,
                created_by=created_by,
            )
        )
        await self.session.flush()
        await self._recalculate_amount_paid(row)

        new_paid = _money2(row.amount_paid)
        after_derived = payable_snapshot_derived_fields(amount_paid=new_paid, amount_final=final)
        if after_derived["is_overpaid"]:
            logger.warning(
                "payables register_payment overpayment detected snapshot_id=%s name=%s "
                "expected_final=%s amount_paid=%s overpaid_amount=%s saldo=%s",
                row.id,
                row.name,
                final,
                new_paid,
                after_derived["overpaid_amount"],
                after_derived["amount_remaining"],
            )

        obs_parts = [f"[pagamento +{amt} em {pd:%d/%m/%Y}]"]
        if after_derived["is_overpaid"]:
            obs_parts.append("(acima do valor esperado)")
        if observation and observation.strip():
            obs_parts.append(observation.strip())
        self._append_observation(row, " ".join(obs_parts))

        logger.info(
            "payables register_payment after snapshot_id=%s amount_paid=%s saldo=%s status=%s "
            "is_overpaid=%s overpaid_amount=%s",
            row.id,
            new_paid,
            after_derived["amount_remaining"],
            after_derived["status"],
            after_derived["is_overpaid"],
            after_derived["overpaid_amount"],
        )
        await self.session.flush()
        return row

    async def reverse_payment(
        self,
        *,
        row: PayableSnapshot,
        amount: float,
        observation: str | None = None,
        reversal_reason: str | None = None,
    ) -> PayableSnapshot:
        amt = _money2(amount)
        if amt <= 0:
            raise ValueError("Valor do estorno deve ser maior que zero.")

        paid_cur = await self._sum_active_payments(row.id)
        if amt > paid_cur + PAYABLE_PAYMENT_TOLERANCE:
            raise ValueError("Valor de estorno maior que o total pago ativo.")

        payments = await self._list_active_payments(row.id, newest_first=True)
        remaining = amt
        reversed_total = Decimal("0.00")
        now = datetime.now(timezone.utc)
        reason = (reversal_reason or "").strip() or None

        for payment in payments:
            if remaining <= PAYABLE_PAYMENT_TOLERANCE:
                break
            p_amt = _money2(payment.amount)
            if p_amt <= remaining + PAYABLE_PAYMENT_TOLERANCE:
                payment.reversed_at = now
                payment.reversal_reason = reason
                reversed_total += p_amt
                remaining = (remaining - p_amt).quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)
            else:
                raise ValueError(
                    f"Estorno parcial do pagamento de {p_amt} não é suportado. "
                    f"Estorne até {p_amt} ou estorne pagamentos mais recentes primeiro."
                )

        if remaining > PAYABLE_PAYMENT_TOLERANCE:
            raise ValueError("Não há pagamentos ativos suficientes para este estorno.")

        await self.session.flush()
        await self._recalculate_amount_paid(row)

        obs_line = f"[estorno -{reversed_total}]"
        if reason:
            obs_line = f"{obs_line} {reason}"
        if observation and observation.strip():
            obs_line = f"{obs_line} — {observation.strip()}"
        self._append_observation(row, obs_line)
        await self.session.flush()
        return row

    async def can_delete_orphaned_row(self, *, row: PayableSnapshot) -> bool:
        """
        Exclusão segura de linhas órfãs/extornadas no snapshot.

        Regras (libera exclusão mesmo que já tenha existido pagamento no passado):
        - não pode ser ANTECIPACAO
        - não pode estar pago (status derivado != PAGO)
        - amount_paid ativo atual == 0 (pagamentos ativos inexistentes)
        - deve estar órfã (fonte removida) para tipos automáticos suportados
        """
        if row.type == PayableSnapshotType.ANTECIPACAO:
            return False

        derived = payable_snapshot_derived_fields(
            amount_paid=_money2(row.amount_paid),
            amount_final=_money2(row.amount_final),
        )
        if str(derived.get("status")) == "PAGO":
            return False

        if await _has_active_payments(self.session, snapshot_id=row.id):
            return False

        if _money2(row.amount_paid) > 0:
            return False

        if row.ref_id is None:
            return False

        # Orfandade: FIXED_COST corporativo (CompanyFinancialItem) ou operacional do projeto.
        if row.type == PayableSnapshotType.FIXED_COST:
            if row.project_id is None:
                src = await self._get_company_financial_item(row.ref_id)
                return src is None or str(getattr(src, "tipo", "")).strip() != "custo_fixo"
            obs = (row.observation or "")
            if SOURCE_TAG_PROJECT_SYSTEM in obs:
                src = await self.session.get(ProjectSystemCost, row.ref_id)
                return src is None
            if SOURCE_TAG_PROJECT_MISC in obs:
                src = await self.session.get(ProjectOperationalFixed, row.ref_id)
                return src is None
            # FIXED_COST legado / desconhecido: não liberar (sem prova de orfandade)
            return False

        # ENDIVIDAMENTO/FINANCIAL corporativo: também pode ficar órfão se item foi removido/substituído.
        if row.type in PAYABLE_DEBT_TYPES and row.project_id is None:
            src = await self._get_company_financial_item(row.ref_id)
            return src is None

        return False

    async def delete_row(self, *, row: PayableSnapshot) -> None:
        await self.session.delete(row)
        await self.session.flush()
