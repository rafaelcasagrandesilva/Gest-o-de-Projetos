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
from app.models.company_finance import (
    CompanyFinancialItem,
    CompanyFinancialItemType,
    CompanyFinancialPayment,
)
from app.models.employee import Employee
from app.models.employee_monthly_payroll_override import EmployeeMonthlyPayrollOverride
from app.models.payment_component import PaymentVariableComponent
from app.models.payable_payment import PayablePayment
from app.models.payable_snapshot import PayableOrigin, PayableSnapshot, PayableSnapshotType
from app.models.payable_snapshot_generation import PayableSnapshotGeneration
from app.models.project_operational import (
    ProjectLabor,
    ProjectOperationalFixed,
    ProjectSystemCost,
)
from app.models.receivable import ReceivableInvoice, ReceivableInvoiceAnticipation
from app.repositories.projects import ProjectRepository
from app.models.project import Project
from app.services.company_finance_cost_center import CompanyFinanceCostCenterService
from app.services.employee_cost_service import (
    calculate_clt_cost,
    calculate_pj_total_cost,
    project_labor_payable_snapshot_components,
)
from app.services.settings_service import SettingsService
from app.utils.dashboard_inclusion import apply_dashboard_inclusion_change
from app.utils.date_utils import next_competencia, normalize_competencia, previous_competencia

logger = logging.getLogger(__name__)

PAYABLE_PAYMENT_TOLERANCE = Decimal("0.02")
_MONEY_QUANT = Decimal("0.01")
PAYABLE_MANUAL_ADJUSTMENT_TAG = "[ajuste manual]"
PAYABLE_CONCILIATED_TAG = "[conciliado]"
# Projetos > Realizado > Veículos: apropriação de custo por projeto (não obrigação financeira).
VEHICLE_AUTO_PAYABLE_NAME = "Custo com veículos"

# Piso de implantação da geração automática de Custos Fixos/Endividamento no Contas a
# Pagar: a funcionalidade NÃO retroage. Competências anteriores a esta NUNCA geram esses
# lançamentos automaticamente (JUL/2026 é a primeira competência válida). Não afeta
# lançamentos de projeto/colaborador, manuais ou antecipações.
COMPANY_FINANCE_AUTOGEN_FIRST_COMPETENCE = date(2026, 7, 1)


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

# Tipos "manuais/preservados": não são regenerados a partir de uma origem mensal —
# sobrevivem à invalidação/regeração do snapshot e ao sync automático, sendo removidos
# apenas por ação explícita. Além do MANUAL histórico (despesa avulsa), inclui as
# obrigações de uma OPERAÇÃO de antecipação (deságio/tarifas/repasse), criadas na
# confirmação do borderô e removidas somente no cancelamento (por ref_id). Estender a
# preservação a esse tipo mantém o comportamento idêntico ao que essas linhas já tinham
# quando eram gravadas como MANUAL — sem alterar nenhuma regra/cálculo de snapshot.
PAYABLE_PRESERVED_TYPES = (PayableSnapshotType.MANUAL, PayableSnapshotType.ANTECIPACAO_OPERACAO)

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
    if row.type in PAYABLE_PRESERVED_TYPES:
        return True
    return _money2(row.amount_paid) > 0


def _payable_row_is_dynamic_sync_protected(row: PayableSnapshot) -> bool:
    """Snapshots que não devem ter valores recalculados automaticamente."""
    if row.type in PAYABLE_PRESERVED_TYPES:
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
                        PayableSnapshot.type.notin_(PAYABLE_PRESERVED_TYPES),
                        PayableSnapshot.amount_paid > 0,
                    )
                )
            )
            or 0
        )

    async def _purge_obsolete_vehicle_snapshots(self, *, month: date) -> int:
        """
        Remove snapshots legados type=VEHICLE sem pagamento (integração descontinuada no CAP).

        Não altera MANUAL nem outros tipos automáticos.
        """
        comp = normalize_competencia(month)
        rows = list(
            (
                await self.session.execute(
                    select(PayableSnapshot).where(
                        PayableSnapshot.month == comp,
                        PayableSnapshot.type == PayableSnapshotType.VEHICLE,
                    )
                )
            )
            .scalars()
            .all()
        )
        removed = 0
        for row in rows:
            if _money2(row.amount_paid) > 0:
                continue
            if await _has_active_payments(self.session, snapshot_id=row.id):
                continue
            await self.session.delete(row)
            removed += 1
        if removed:
            logger.info(
                "payables purged obsolete VEHICLE snapshots month=%s removed=%d",
                comp,
                removed,
            )
        await self.session.flush()
        return removed

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
                    PayableSnapshot.type.notin_(PAYABLE_PRESERVED_TYPES),
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

    async def _ensure_company_finance_auto_entries(self, *, payment_month: date) -> int:
        """Backfill idempotente de Custos Fixos/Endividamento na competência.

        Antes dependia de valor lançado manualmente na matriz (`company_financial_payments`);
        agora o CADASTRO governa e a geração é automática a partir do valor de referência
        (ver `_generate_company_finance_payables`). Mantido como ponto de extensão chamado
        na abertura/sincronização do mês.
        """
        return await self._generate_company_finance_payables(payment_month=payment_month)

    async def _get_company_financial_item(self, item_id: UUID) -> CompanyFinancialItem | None:
        """Carrega item sem lazy load async (cost_center_project/employee via selectinload)."""
        stmt = (
            select(CompanyFinancialItem)
            .where(CompanyFinancialItem.id == item_id)
            .options(
                selectinload(CompanyFinancialItem.cost_center_project),
                selectinload(CompanyFinancialItem.employee),
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    @staticmethod
    def _company_finance_payable_identity(item: CompanyFinancialItem) -> tuple[str, str | None]:
        """(name, item_description) exibidos no Contas a Pagar.

        Padrão único (igual ao Custos Fixos): `name` identifica o item e `item_description`
        apenas complementa (subtítulo, opcional).

        Endividamento: `name` = colaborador vinculado (tipo Colaborador) ou o próprio
        `item.nome` (tipo Manual); `item_description` = descrição complementar quando houver.
        Para não duplicar, a descrição é omitida quando coincide com o nome (compatível com
        cadastros legados onde o nome era composto a partir da descrição). Demais tipos
        (custo fixo/projeto): `name` = `item.nome`, `item_description` = None (inalterado).
        """
        if item.tipo == "endividamento":
            emp = getattr(item, "employee", None)
            emp_name = _employee_display_name(emp) if emp is not None else None
            name = (emp_name or str(item.nome or "")).strip() or str(item.nome or "")
            desc = (getattr(item, "item_description", None) or "").strip() or None
            if desc is not None and desc.casefold() == name.casefold():
                desc = None  # evita subtítulo duplicado (nome == descrição)
            return name, desc
        return str(item.nome or "").strip(), None

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

    # ------------------------------------------------------------------ #
    # Geração automática a partir do CADASTRO (Custos Fixos / Endividamento)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _company_finance_payable_labels(item: CompanyFinancialItem) -> tuple[PayableSnapshotType, str, str]:
        """(type, category, origin) do lançamento conforme as regras do cadastro.

        - Custo fixo vinculado a colaborador → Tipo "Colaborador" (o credor/nome é o
          próprio colaborador, já gravado em `item.nome`);
        - Custo fixo sem colaborador → Tipo "Custo Fixo";
        - Endividamento → Tipo "Endividamento".

        O `type` interno permanece FIXED_COST/ENDIVIDAMENTO (reconciliação por ref_id
        intacta); o rótulo exibido vem da `category`.
        """
        if item.tipo == "endividamento":
            return PayableSnapshotType.ENDIVIDAMENTO, "Endividamento", PayableOrigin.DEBT.value
        if getattr(item, "employee_id", None) is not None:
            return PayableSnapshotType.FIXED_COST, "Colaborador", PayableOrigin.FIXED_COST.value
        return PayableSnapshotType.FIXED_COST, "Custo Fixo", PayableOrigin.FIXED_COST.value

    def _company_finance_monthly_value(
        self, item: CompanyFinancialItem, *, comp: date, settings
    ) -> Decimal:
        """Valor mensal do lançamento automático (congelado no snapshot).

        - Custo fixo colaborador (COLABORADOR_MATRIZ): custo do colaborador no mês × %;
        - Custo fixo comum: valor mensal de referência;
        - Endividamento: parcela prevista (installment_value) ou saldo/valor de referência
          — mesma base já usada pelas pendências, sem alterar cálculo financeiro.
        """
        if item.tipo == "custo_fixo":
            emp = getattr(item, "employee", None)
            pct = getattr(item, "percentual", None)
            if (
                getattr(item, "item_type", None) == CompanyFinancialItemType.COLABORADOR_MATRIZ
                and emp is not None
                and pct is not None
            ):
                if (getattr(emp, "employment_type", "") or "").upper() == "CLT":
                    base = calculate_clt_cost(emp, settings, comp.year, comp.month)
                else:
                    base = calculate_pj_total_cost(emp)
                return _money2(float(base) * (float(pct) / 100.0))
            return _money2(item.valor_referencia)
        # Endividamento
        rt = getattr(item, "renegotiation_type", None)
        rt_val = getattr(rt, "value", rt)
        if (
            getattr(item, "has_renegotiation", False)
            and rt_val == "INSTALLMENTS"
            and getattr(item, "installment_value", None) is not None
        ):
            return _money2(item.installment_value)
        if getattr(item, "has_renegotiation", False) and getattr(item, "renegotiated_amount", None) is not None:
            return _money2(item.renegotiated_amount)
        return _money2(item.valor_referencia)

    def _company_finance_item_eligible_for_comp(
        self, item: CompanyFinancialItem, comp: date
    ) -> bool:
        """Item elegível a lançamento automático na competência (ciclo de vida + vigência).

        Mesma regra da geração, SEM o piso de implantação: item ativo, vigência cobrindo o
        mês e, para endividamento, "Obrigatório mensal". Usada para materializar a linha
        quando o usuário informa explicitamente o valor da competência na grade (manutenção
        de competência ABERTA anterior ao piso — ex.: DEX em Junho).
        """
        if not bool(getattr(item, "is_active", True)):
            return False
        _, month_end = _month_bounds(comp)
        start = getattr(item, "start_date", None)
        end = getattr(item, "end_date", None)
        if start is not None and start > month_end:
            return False
        if end is not None and end < comp:
            return False
        if item.tipo == "endividamento" and not bool(getattr(item, "is_monthly_required", False)):
            return False
        return True


    async def _company_finance_entries_for_month(
        self, *, item_id: UUID, comp: date
    ) -> list[CompanyFinancialPayment]:
        """Lançamentos (grade) de um item na competência, ordenados por vencimento → criação.

        Ordenação estável e determinística (requisito de UX): `due_date` ascendente (NULLs por
        último) e, no empate, `created_at`. Não depende da ordem de inserção pelo usuário.
        """
        rows = (
            await self.session.execute(
                select(CompanyFinancialPayment)
                .where(
                    CompanyFinancialPayment.item_id == item_id,
                    CompanyFinancialPayment.competencia == normalize_competencia(comp),
                )
                .order_by(
                    CompanyFinancialPayment.due_date.asc().nulls_last(),
                    CompanyFinancialPayment.created_at.asc(),
                )
            )
        ).scalars().all()
        return list(rows)

    async def _reconcile_company_finance_entries_for_month(
        self,
        *,
        item: CompanyFinancialItem,
        comp: date,
        settings,
        cc_svc: CompanyFinanceCostCenterService,
        is_generating: bool,
    ) -> dict:
        """Reconciliador ÚNICO grade→CAP por (item, competência), com N lançamentos.

        Invariante alvo: cada LANÇAMENTO da competência ↔ um título do Contas a Pagar
        (`entry_id`). Encapsula toda a lógica de múltiplos lançamentos no pipeline do CAP —
        para quem consome o CAP a mudança é transparente (apenas muda a granularidade).

        Ações (idempotentes, genéricas para qualquer item de Custo Fixo/Endividamento):
        - materializa 1 lançamento de REFERÊNCIA quando o item é elegível e a competência não
          tem nenhum lançamento nem título (comportamento idêntico à geração atual);
        - para cada lançamento: adota um título legado não vinculado (entry_id NULL) equivalente
          ou cria o título; atualiza valor/vencimento de títulos ABERTOS; preserva títulos com
          pagamento (reporta em `skipped_paid`);
        - NÃO remove títulos aqui (exclusão de lançamento é explícita em `replace_entries`, que
          apaga o título ABERTO antes de apagar o lançamento; títulos pagos permanecem e são
          tratados pela reconciliação por `entry_id`).

        `is_generating`: True durante a geração do mês (o marcador ainda não existe) — permite
        criar títulos; fora da geração, só cria se a competência já estiver materializada
        (`is_generated`), como no fluxo atual. Retorna {"synced", "created", "skipped_paid"}.
        """
        comp = normalize_competencia(comp)
        below_floor = comp < COMPANY_FINANCE_AUTOGEN_FIRST_COMPETENCE
        can_create = is_generating or await self.is_generated(month=comp)
        eligible = self._company_finance_item_eligible_for_comp(item, comp)

        entries = await self._company_finance_entries_for_month(item_id=item.id, comp=comp)

        cap_lines = (
            await self.session.execute(
                select(PayableSnapshot).where(
                    PayableSnapshot.ref_id == item.id,
                    PayableSnapshot.month == comp,
                    PayableSnapshot.project_id.is_(None),
                    PayableSnapshot.type.in_((PayableSnapshotType.FIXED_COST, *PAYABLE_DEBT_TYPES)),
                )
            )
        ).scalars().all()
        linked: dict[UUID, PayableSnapshot] = {l.entry_id: l for l in cap_lines if l.entry_id is not None}
        unlinked: list[PayableSnapshot] = [l for l in cap_lines if l.entry_id is None]

        result = {"synced": 0, "created": 0, "skipped_paid": []}

        # Materializa o lançamento de referência quando não há nada (elegível, acima do piso).
        if not entries and not cap_lines:
            if below_floor or not eligible or not can_create:
                return result
            value = self._company_finance_monthly_value(item, comp=comp, settings=settings)
            if value <= 0:
                return result
            entry = CompanyFinancialPayment(
                item_id=item.id,
                competencia=comp,
                valor=value,
                due_date=_default_due_date(comp, day=10),
                descricao=None,
            )
            self.session.add(entry)
            await self.session.flush()
            entries = [entry]

        if not entries:
            return result  # sem lançamentos (mas há títulos legados órfãos) → não mexe

        snap_type, category, origin = self._company_finance_payable_labels(item)
        cost_center = await cc_svc.resolve_label(item)
        name, item_description = self._company_finance_payable_identity(item)

        for entry in entries:
            new_amount = _money2(entry.valor)
            due = entry.due_date or _default_due_date(comp, day=10)
            # Descrição do LANÇAMENTO vira o subtítulo do título (mesmo padrão do Endividamento
            # e dos Componentes Variáveis). Vazia → cai no `item_description` do item (descrição
            # da dívida em Endividamento; None em Custos Fixos). Genérico p/ qualquer fornecedor.
            line_item_description = (entry.descricao or "").strip() or item_description
            row = linked.get(entry.id)

            # Adoção de título legado equivalente (entry_id NULL) — vincula em vez de duplicar.
            if row is None and unlinked:
                row = unlinked.pop(0)
                row.entry_id = entry.id
                linked[entry.id] = row

            if row is None:
                # Cria o título apenas para item elegível e competência materializável.
                if not (eligible and can_create) or new_amount <= 0:
                    continue
                row = PayableSnapshot(
                    month=comp,
                    type=snap_type,
                    ref_id=item.id,
                    entry_id=entry.id,
                    project_id=None,
                    name=name,
                    item_description=line_item_description,
                    cost_center=cost_center,
                    category=category,
                    origin=origin,
                    amount_original=new_amount,
                    amount_final=new_amount,
                    amount_paid=Decimal("0"),
                    due_date=due,
                    paid=False,
                    payment_date=None,
                    observation=None,
                )
                self.session.add(row)
                linked[entry.id] = row
                result["created"] += 1
                result["synced"] += 1
                continue

            # Título existente: metadados sempre coerentes (não alteram valor/pagamento).
            row.name = name
            row.item_description = line_item_description
            row.cost_center = cost_center
            row.category = category
            if not row.origin:
                row.origin = origin

            has_payment = _money2(row.amount_paid) > 0 or await _has_active_payments(
                self.session, snapshot_id=row.id
            )
            if has_payment:
                # Preserva o histórico: nunca altera valor/vencimento de título com pagamento.
                if _money2(row.amount_final) != new_amount or row.due_date != due:
                    result["skipped_paid"].append(comp)
                _sync_legacy_paid_fields(row)
                continue

            changed = False
            if _money2(row.amount_final) != new_amount or _money2(row.amount_original) != new_amount:
                before_o, before_f, before_p = (
                    _money2(row.amount_original),
                    _money2(row.amount_final),
                    _money2(row.amount_paid),
                )
                _apply_dynamic_payable_amounts(row, new_amount=new_amount)
                _log_payable_dynamic_sync(
                    action="entry_sync",
                    row=row,
                    before_original=before_o,
                    before_final=before_f,
                    before_paid=before_p,
                )
                changed = True
            if row.due_date != due:
                row.due_date = due
                changed = True
            if changed:
                result["synced"] += 1

        await self.session.flush()
        return result

    async def _generate_company_finance_payables(self, *, payment_month: date) -> int:
        """Gera automaticamente os lançamentos de Custos Fixos e Endividamento (por LANÇAMENTO).

        O CADASTRO governa a linha de contas a pagar. Delega ao reconciliador único por item:
        - Custos Fixos: item ativo e competência dentro da vigência (início/encerramento);
        - Endividamento: além disso, apenas quando `is_monthly_required` (Obrigatório = Sim).
        Cada LANÇAMENTO da competência vira um título independente; quando não há lançamento, um
        de REFERÊNCIA é materializado (acima do piso JUL/2026). Idempotente (não duplica nem
        apaga). O piso preserva o histórico: abaixo dele só há título a partir de lançamento
        explícito (grade), nunca da referência.
        """
        comp = normalize_competencia(payment_month)
        _, month_end = _month_bounds(comp)
        settings = await SettingsService(self.session).get_or_create()
        cc_svc = CompanyFinanceCostCenterService(self.session)

        # Itens ativos cuja vigência cobre a competência.
        stmt = (
            select(CompanyFinancialItem)
            .options(
                selectinload(CompanyFinancialItem.employee),
                selectinload(CompanyFinancialItem.cost_center_project),
            )
            .where(
                CompanyFinancialItem.tipo.in_(("custo_fixo", "endividamento")),
                CompanyFinancialItem.is_active.is_(True),
                or_(CompanyFinancialItem.start_date.is_(None), CompanyFinancialItem.start_date <= month_end),
                or_(CompanyFinancialItem.end_date.is_(None), CompanyFinancialItem.end_date >= comp),
            )
        )
        items = list((await self.session.execute(stmt)).scalars().unique().all())
        if not items:
            return 0

        created = 0
        for item in items:
            res = await self._reconcile_company_finance_entries_for_month(
                item=item, comp=comp, settings=settings, cc_svc=cc_svc, is_generating=True
            )
            created += int(res.get("created", 0))

        if created:
            logger.info("payables company_finance auto-generation month=%s created=%d", comp, created)
        return created

    async def purge_pre_launch_company_finance_payables(
        self,
        *,
        first_competence: date = COMPANY_FINANCE_AUTOGEN_FIRST_COMPETENCE,
        dry_run: bool = False,
    ) -> dict:
        """Limpeza segura dos lançamentos automáticos de Custos Fixos/Endividamento criados
        indevidamente em competências ANTERIORES à implantação (< first_competence).

        Remove apenas linhas que atendem TODAS as condições (100% seguro):
        - origin ∈ (FIXED_COST, DEBT)  → gerados automaticamente pelo cadastro corporativo;
        - competência < first_competence (JUL/2026);
        - sem QUALQUER pagamento registrado: amount_paid <= 0 E sem linha em payable_payments
          (ativa ou estornada);
        - SEM valor informado na grade mensal (`company_financial_payments`) para aquela
          competência: linhas com valor de grade representam manutenção DELIBERADA de uma
          competência aberta (ex.: DEX em Junho) e são preservadas.

        NUNCA remove: manuais (origin MANUAL), de projeto/colaborador (origin PROJECT/NULL),
        antecipações, linhas com pagamento nem linhas com valor informado na grade.
        `dry_run=True` apenas conta (não deleta). Retorna relatório.
        """
        first = normalize_competencia(first_competence)
        stmt = (
            select(PayableSnapshot)
            .where(
                PayableSnapshot.month < first,
                PayableSnapshot.origin.in_(
                    (PayableOrigin.FIXED_COST.value, PayableOrigin.DEBT.value)
                ),
                PayableSnapshot.amount_paid <= 0,
                ~PayableSnapshot.id.in_(select(PayablePayment.payable_snapshot_id)),
            )
            .order_by(PayableSnapshot.month.asc())
        )
        rows = list((await self.session.execute(stmt)).scalars().all())

        # Preserva linhas cujo valor foi informado explicitamente na grade mensal para aquela
        # competência (manutenção deliberada de competência aberta anterior ao piso).
        grid_pairs: set[tuple[UUID, date]] = set()
        ref_ids = {r.ref_id for r in rows if r.ref_id is not None}
        if ref_ids:
            grid_rows = (
                await self.session.execute(
                    select(
                        CompanyFinancialPayment.item_id, CompanyFinancialPayment.competencia
                    ).where(
                        CompanyFinancialPayment.item_id.in_(ref_ids),
                        CompanyFinancialPayment.competencia < first,
                    )
                )
            ).all()
            grid_pairs = {(iid, normalize_competencia(c)) for iid, c in grid_rows}
        rows = [
            r
            for r in rows
            if r.ref_id is None
            or (r.ref_id, normalize_competencia(r.month)) not in grid_pairs
        ]

        by_competence: dict[str, int] = {}
        for r in rows:
            key = f"{r.month:%Y-%m}"
            by_competence[key] = by_competence.get(key, 0) + 1
            if not dry_run:
                await self.session.delete(r)
        if not dry_run:
            await self.session.flush()
            if rows:
                logger.warning(
                    "payables purge pre-launch company_finance removed=%d competences=%s",
                    len(rows),
                    sorted(by_competence),
                )
        return {
            "first_competence": f"{first:%Y-%m}",
            "removed": 0 if dry_run else len(rows),
            "candidates": len(rows),
            "by_competence": dict(sorted(by_competence.items())),
            "dry_run": dry_run,
        }

    async def sync_competencia(
        self,
        *,
        payment_month: date,
        accessible_project_ids: set[UUID] | None = None,
        sees_all_projects: bool = True,
    ) -> list[PayableSnapshot]:
        """Rotina reutilizável de sincronização de uma competência.

        Garante que o snapshot da competência exista (custos de Projetos) e gera os
        lançamentos automáticos faltantes de Custos Fixos/Endividamento. É idempotente
        (pode rodar infinitas vezes), NUNCA duplica, NUNCA apaga lançamentos existentes
        nem lançamentos manuais. Base para todas as automações futuras.
        """
        rows = await self.get_or_create_for_month(
            payment_month=payment_month,
            accessible_project_ids=accessible_project_ids,
            sees_all_projects=sees_all_projects,
        )
        return rows

    async def sync_company_finance_item_metadata(self, *, item_id: UUID) -> int:
        """
        Atualiza nome/centro/categoria em snapshots corporativos existentes.

        Nunca apaga linhas nem altera valores (`amount_*`). Usado em edição estrutural.
        """
        item = await self._get_company_financial_item(item_id)
        if item is None:
            return 0
        _snap_type, cost_center, category = await self._company_finance_snapshot_meta(item)
        name, item_description = self._company_finance_payable_identity(item)
        # Descrição por LANÇAMENTO é o subtítulo oficial da linha — preservada aqui (edição de
        # cadastro atualiza nome/centro/categoria, mas NÃO deve apagar a descrição do lançamento).
        entry_desc = {
            e.id: (e.descricao or "").strip() or None
            for e in (
                await self.session.execute(
                    select(CompanyFinancialPayment).where(CompanyFinancialPayment.item_id == item_id)
                )
            ).scalars().all()
        }
        rows = (
            await self.session.execute(
                select(PayableSnapshot).where(
                    PayableSnapshot.ref_id == item_id,
                    PayableSnapshot.type.in_((PayableSnapshotType.FIXED_COST, *PAYABLE_DEBT_TYPES)),
                )
            )
        ).scalars().all()
        for row in rows:
            row.name = name
            row.item_description = entry_desc.get(row.entry_id) or item_description
            row.cost_center = cost_center
            row.category = category
            _sync_legacy_paid_fields(row)
        await self.session.flush()
        return len(rows)

    async def sync_company_finance_item_months(
        self, *, item_id: UUID, months: set[date]
    ) -> dict:
        """A grade mensal governa o valor oficial da competência no Contas a Pagar.

        Regra funcional (Custos Fixos/Endividamento):
        - a geração (`_generate_company_finance_payables`) cria a linha das competências
          elegíveis; o valor oficial da competência é o valor informado na grade mensal
          (`company_financial_payments`) quando existir e, senão, o valor de REFERÊNCIA;
        - editar a caixa do mês atualiza o lançamento correspondente do CAP
          (amount_original E amount_final → NÃO gera saldo/crédito/ajuste; apenas define o
          valor oficial). Sem valor na grade → volta ao valor de referência (fallback).

        Localiza a linha por (tipo corporativo FIXED_COST/ENDIVIDAMENTO) + `ref_id` +
        `month`. Se a linha existir e estiver ABERTA, atualiza; havendo pagamento, preserva
        o histórico e reporta o mês para aviso ao usuário. Se a linha NÃO existir e o
        usuário informou explicitamente o valor na grade (competência aberta, mês já
        materializado, item elegível), a linha é CRIADA — inclusive em competências
        anteriores ao piso JUL/2026 (manutenção de competência aberta, ex.: DEX em Junho).
        O piso só bloqueia ação baseada SOMENTE na referência (sem valor na grade), para
        preservar o histórico e não retroagir. Não altera Dashboard/KPIs paga/consolidada.

        Suporta N LANÇAMENTOS por competência: delega ao reconciliador único
        (`_reconcile_company_finance_entries_for_month`), que trata materialização,
        adoção de título legado, criação/atualização por lançamento e guarda de pagamento.

        Retorna {"synced": int, "skipped_paid": list[date]}.
        """
        synced = 0
        skipped_paid: list[date] = []
        if not months:
            return {"synced": 0, "skipped_paid": []}

        item = await self._get_company_financial_item(item_id)
        if item is None:
            return {"synced": 0, "skipped_paid": []}
        settings = await SettingsService(self.session).get_or_create()
        cc_svc = CompanyFinanceCostCenterService(self.session)

        for raw_month in months:
            comp = normalize_competencia(raw_month)
            res = await self._reconcile_company_finance_entries_for_month(
                item=item, comp=comp, settings=settings, cc_svc=cc_svc, is_generating=False
            )
            synced += int(res.get("synced", 0))
            skipped_paid.extend(res.get("skipped_paid", []))

        if synced or skipped_paid:
            await self.session.flush()
        return {"synced": synced, "skipped_paid": skipped_paid}

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

    # ------------------------------------------------------------------ #
    # Componentes Variáveis de Pagamento (Projeto e Custo Fixo) — pipeline único
    # ------------------------------------------------------------------ #
    async def _variable_component_snapshot_fields(
        self, component: PaymentVariableComponent
    ) -> dict | None:
        """Campos do snapshot de um componente variável, ESPELHANDO a origem financeira:
        Projeto → COLLABORATOR (mês de pagamento = competência + 1); Custo Fixo →
        FIXED_COST/categoria "Colaborador" (mês = competência). Valor INTEGRAL (sem rateio).

        Retorna None quando não deve existir snapshot (valor <= 0, contexto ausente/apagado).
        """
        amount = _money2(component.amount)
        if amount <= 0:
            return None
        emp = await self.session.get(Employee, component.employee_id)
        if emp is None:
            return None
        display = _employee_display_name(emp)
        type_name = (getattr(component.type, "name", None) or "Componente").strip()
        name = _collaborator_payable_snapshot_name(display, type_name)

        if component.project_labor_id is not None:
            labor = await self.session.get(ProjectLabor, component.project_labor_id)
            if labor is None:
                return None
            # CAP reflete apenas REALIZADO: componente em labor PREVISTO é salvo, mas não
            # materializa lançamento (mesma regra do salário).
            if coerce_scenario(labor.scenario) != Scenario.REALIZADO:
                return None
            proj = await self.session.get(Project, labor.project_id)
            if proj is None or getattr(proj, "deleted_at", None) is not None:
                return None
            return {
                "month": next_competencia(normalize_competencia(component.competencia)),
                "type": PayableSnapshotType.COLLABORATOR,
                "project_id": proj.id,
                "cost_center": str(proj.name).strip(),
                "category": "Mão de obra",
                "name": name,
                "amount": amount,
            }

        item = await self._get_company_financial_item(component.company_financial_item_id)
        if item is None:
            return None
        cc = await CompanyFinanceCostCenterService(self.session).resolve_label(item)
        return {
            "month": normalize_competencia(component.competencia),
            "type": PayableSnapshotType.FIXED_COST,
            "project_id": None,
            "cost_center": cc,
            "category": "Colaborador",  # payable_display classifica FIXED_COST+Colaborador como folha
            "name": name,
            "amount": amount,
        }

    async def _find_variable_snapshot(self, component_id: UUID) -> PayableSnapshot | None:
        return (
            await self.session.execute(
                select(PayableSnapshot).where(
                    PayableSnapshot.origin == PayableOrigin.VARIABLE.value,
                    PayableSnapshot.ref_id == component_id,
                )
            )
        ).scalars().first()

    async def apply_variable_component(self, *, component: PaymentVariableComponent) -> None:
        """Upsert IDEMPOTENTE do snapshot do componente (identidade: origin=VARIABLE + ref_id).

        Rodar N vezes converge ao mesmo snapshot. Linha já paga é preservada (histórico).
        """
        fields = await self._variable_component_snapshot_fields(component)
        existing = await self._find_variable_snapshot(component.id)

        if fields is None:
            if existing is not None and _money2(existing.amount_paid) <= 0 and not await _has_active_payments(
                self.session, snapshot_id=existing.id
            ):
                await self.session.delete(existing)
            await self.session.flush()
            return

        if existing is None:
            self.session.add(
                PayableSnapshot(
                    month=fields["month"],
                    type=fields["type"],
                    ref_id=component.id,
                    project_id=fields["project_id"],
                    name=fields["name"],
                    item_description=(component.note or None),
                    cost_center=fields["cost_center"],
                    category=fields["category"],
                    origin=PayableOrigin.VARIABLE.value,
                    amount_original=fields["amount"],
                    amount_final=fields["amount"],
                    amount_paid=Decimal("0"),
                    due_date=_default_due_date(fields["month"], day=10),
                    paid=False,
                    payment_date=None,
                    observation=None,
                )
            )
            await self.session.flush()
            return

        # Já pago: nunca altera valor/identidade (preserva histórico financeiro).
        if _money2(existing.amount_paid) > 0 or await _has_active_payments(
            self.session, snapshot_id=existing.id
        ):
            await self.session.flush()
            return

        existing.month = fields["month"]
        existing.type = fields["type"]
        existing.project_id = fields["project_id"]
        existing.name = fields["name"]
        existing.item_description = component.note or None
        existing.cost_center = fields["cost_center"]
        existing.category = fields["category"]
        _apply_dynamic_payable_amounts(existing, new_amount=fields["amount"])
        await self.session.flush()

    async def remove_variable_component_snapshot(self, *, component_id: UUID) -> bool:
        """Remove o snapshot do componente. Retorna False (bloqueia) se já houver pagamento."""
        existing = await self._find_variable_snapshot(component_id)
        if existing is None:
            return True
        if _money2(existing.amount_paid) > 0 or await _has_active_payments(
            self.session, snapshot_id=existing.id
        ):
            return False
        await self.session.delete(existing)
        await self.session.flush()
        return True

    async def sync_all_variable_components_for_month(self, *, payment_month: date) -> int:
        """Materializa (idempotente) todos os componentes variáveis pagos neste mês e remove
        snapshots VARIABLE órfãos (componente apagado). Chamado na abertura/sync do mês.

        Projeto: componente cujo project_labor REALIZADO está na competência anterior.
        Custo Fixo: componente cuja competência é o próprio mês de pagamento.
        """
        comp = normalize_competencia(payment_month)
        source = previous_competencia(comp)

        proj_components = list(
            (
                await self.session.execute(
                    select(PaymentVariableComponent)
                    .join(ProjectLabor, PaymentVariableComponent.project_labor_id == ProjectLabor.id)
                    .where(
                        PaymentVariableComponent.project_labor_id.is_not(None),
                        ProjectLabor.competencia == source,
                        ProjectLabor.scenario == scenario_pg_rhs(Scenario.REALIZADO),
                    )
                )
            ).scalars().all()
        )
        fixed_components = list(
            (
                await self.session.execute(
                    select(PaymentVariableComponent).where(
                        PaymentVariableComponent.company_financial_item_id.is_not(None),
                        PaymentVariableComponent.competencia == comp,
                    )
                )
            ).scalars().all()
        )

        valid_ids: set[UUID] = set()
        changed = 0
        for c in [*proj_components, *fixed_components]:
            await self.apply_variable_component(component=c)
            valid_ids.add(c.id)
            changed += 1

        # Remove snapshots VARIABLE do mês cujo componente não existe mais (sem pagamento).
        existing_var = list(
            (
                await self.session.execute(
                    select(PayableSnapshot).where(
                        PayableSnapshot.month == comp,
                        PayableSnapshot.origin == PayableOrigin.VARIABLE.value,
                    )
                )
            ).scalars().all()
        )
        for row in existing_var:
            if row.ref_id in valid_ids:
                continue
            if _money2(row.amount_paid) > 0 or await _has_active_payments(self.session, snapshot_id=row.id):
                continue
            await self.session.delete(row)
            changed += 1

        await self.session.flush()
        return changed

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
                        added_fixed = await self._ensure_company_finance_auto_entries(payment_month=comp)
                        added_ants = await self._ensure_invoice_anticipation_obligations(
                            payment_month=comp,
                            project_ids=None if sees_all_projects else (accessible_project_ids or None),
                        )
                        added_var = await self.sync_all_variable_components_for_month(payment_month=comp)
                        if added_fixed or added_ants or added_var:
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
                        added_fixed = await self._ensure_company_finance_auto_entries(payment_month=comp)
                        added_ants = await self._ensure_invoice_anticipation_obligations(
                            payment_month=comp,
                            project_ids=None if sees_all_projects else (accessible_project_ids or None),
                        )
                        added_var = await self.sync_all_variable_components_for_month(payment_month=comp)
                        if added_fixed or added_ants or added_var:
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
                await self._purge_obsolete_vehicle_snapshots(month=comp)
                await self.session.execute(
                    delete(PayableSnapshot).where(
                        PayableSnapshot.month == comp,
                        PayableSnapshot.type.notin_(PAYABLE_PRESERVED_TYPES),
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
                                PayableSnapshot.type.notin_(PAYABLE_PRESERVED_TYPES),
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

            if created <= 0 and (await self.count_for_month(month=comp)) <= 0:
                logger.info(
                    "payables snapshot month=%s finalized with 0 rows (empty month is valid) force=%s",
                    comp,
                    force_regenerate,
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
        """
        Gera linhas automáticas do contas a pagar para o mês de pagamento.

        Custos de veículos (Projetos > Realizado > Veículos) são excluídos: são
        apropriação operacional por projeto; combustível/locação é faturado em lote.
        """
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

            # --- Company finance: Custos Fixos + Endividamento (geração automática) ---
            # O CADASTRO governa a linha (valor de referência), respeitando o ciclo de
            # vida (ativo + vigência) e, para endividamento, o "Obrigatório = Sim".
            # Idempotente por (competência, ref_id) — ver _generate_company_finance_payables.
            created += await self._generate_company_finance_payables(payment_month=payment_month)

            # --- Componentes Variáveis de Pagamento (Projeto + Custo Fixo) — pipeline único ---
            created += await self.sync_all_variable_components_for_month(payment_month=payment_month)

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
                "fixed_items=%d created=%d",
                payment_month,
                source_month,
                sees_all_projects,
                "ALL" if sees_all_projects else (len(project_filter) if project_filter is not None else 0),
                len(keys),
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
        include_in_dashboard: bool = True,
        ref_id: UUID | None = None,
    ) -> PayableSnapshot:
        # Manual: competência = mês do vencimento (obrigação), não o mês do filtro da tela.
        comp = normalize_competencia(due_date)
        amt = Decimal(str(round(float(amount), 2)))
        cc = await self._validate_manual_cost_center(cost_center)
        obs = (observation or "").strip() or None
        origin = (
            PayableOrigin.ANTECIPACAO.value
            if snapshot_type == PayableSnapshotType.ANTECIPACAO_OPERACAO
            else PayableOrigin.MANUAL.value
        )
        row = PayableSnapshot(
            month=comp,
            type=snapshot_type,
            # ref_id permite vincular o lançamento à operação de antecipação (rastreabilidade).
            ref_id=ref_id or uuid4(),
            project_id=None,
            origin=origin,
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
            include_in_dashboard=bool(include_in_dashboard),
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def update_row(
        self,
        *,
        row: PayableSnapshot,
        amount_final: float | None,
        due_date: date | None,
        observation: str | None,
        include_in_dashboard: bool | None = None,
    ) -> PayableSnapshot:
        if amount_final is not None:
            row.amount_final = Decimal(str(round(float(amount_final), 2)))
            self._append_observation(row, PAYABLE_MANUAL_ADJUSTMENT_TAG)
        if due_date is not None:
            row.due_date = due_date
        if observation is not None:
            row.observation = observation
        apply_dashboard_inclusion_change(
            before=bool(row.include_in_dashboard),
            after=include_in_dashboard,
            set_value=lambda v: setattr(row, "include_in_dashboard", v),
            append_line=lambda line: self._append_observation(row, line),
        )
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

    async def _collaborator_labor_exists(
        self, *, employee_id: UUID, project_id: UUID, source_month: date
    ) -> bool:
        """Existe a folha (ProjectLabor) que originou o snapshot COLLABORATOR?

        Espelha EXATAMENTE a chave da geração (service: keys_stmt): mesmo
        employee_id + project_id, no `source_month`, cenário REALIZADO e
        alocação > 0. Um mesmo ProjectLabor pode gerar várias linhas (componentes
        no nome); a chave cobre todas de forma consistente.
        """
        stmt = (
            select(func.count())
            .select_from(ProjectLabor)
            .where(
                ProjectLabor.employee_id == employee_id,
                ProjectLabor.project_id == project_id,
                ProjectLabor.competencia == source_month,
                ProjectLabor.scenario == scenario_pg_rhs(Scenario.REALIZADO),
                ProjectLabor.allocation_percentage > 0,
            )
        )
        return int((await self.session.execute(stmt)).scalar_one() or 0) > 0

    async def origin_is_missing(self, *, row: PayableSnapshot) -> bool | None:
        """Regra ÚNICA de orfandade: a origem atual do lançamento automático sumiu?

        Retorno:
        - True  → origem removida (lançamento é resíduo/obsoleto);
        - False → origem ainda existe (manter);
        - None  → não rastreável até uma origem única (MANUAL, ref_id ausente,
                  FIXED_COST legado agregado, VEHICLE legado) → não decidir.

        Mapeamento por tipo (espelha exatamente a geração do snapshot):
        - COLLABORATOR  → employees.id
        - ANTECIPACAO   → receivable_invoice_anticipations.id
        - FIXED_COST    → CompanyFinancialItem (corporativo, project_id nulo) /
                          ProjectSystemCost / ProjectOperationalFixed (por tag)
        - ENDIVIDAMENTO/FINANCIAL → CompanyFinancialItem
        """
        if row.type in PAYABLE_PRESERVED_TYPES:
            return None
        if row.ref_id is None:
            return None
        # Componentes Variáveis de Pagamento: a sincronização (rebuild na mesma transação
        # do CRUD) é a fonte de verdade; a reconciliação nunca os marca como órfãos.
        if (row.origin or "") == PayableOrigin.VARIABLE.value:
            return None

        if row.type == PayableSnapshotType.COLLABORATOR:
            # A origem econômica real é a folha (ProjectLabor) do mês-origem usado
            # na geração (source_month = mês anterior ao pagamento), NÃO a mera
            # existência do Employee — um colaborador pode permanecer no cadastro
            # após ter sua folha/alocação removida. Sem project_id não há folha
            # rastreável até uma origem única.
            if row.project_id is None:
                return None
            source_month = previous_competencia(row.month)
            return not await self._collaborator_labor_exists(
                employee_id=row.ref_id,
                project_id=row.project_id,
                source_month=source_month,
            )

        if row.type == PayableSnapshotType.ANTECIPACAO:
            return await self.session.get(ReceivableInvoiceAnticipation, row.ref_id) is None

        if row.type == PayableSnapshotType.FIXED_COST:
            if row.project_id is None:
                src = await self._get_company_financial_item(row.ref_id)
                if src is None or str(getattr(src, "tipo", "")).strip() != "custo_fixo":
                    return True
                # Múltiplos lançamentos: a origem precisa é o LANÇAMENTO (entry_id). Título
                # cujo lançamento foi removido é resíduo. Legado sem vínculo (entry_id NULL)
                # segue regido pela existência do ITEM (compatibilidade).
                if row.entry_id is not None:
                    return await self.session.get(CompanyFinancialPayment, row.entry_id) is None
                return False
            obs = row.observation or ""
            if SOURCE_TAG_PROJECT_SYSTEM in obs:
                return await self.session.get(ProjectSystemCost, row.ref_id) is None
            if SOURCE_TAG_PROJECT_MISC in obs:
                return await self.session.get(ProjectOperationalFixed, row.ref_id) is None
            # FIXED_COST legado / desconhecido: sem prova de orfandade.
            return None

        if row.type in PAYABLE_DEBT_TYPES:  # ENDIVIDAMENTO, FINANCIAL
            src = await self._get_company_financial_item(row.ref_id)
            if src is None:
                return True
            # Endividamento permanece single-lançamento; quando vinculado, órfão = lançamento
            # removido (mantém coerência com Custos Fixos sem alterar a UI/renegociação).
            if row.entry_id is not None:
                return await self.session.get(CompanyFinancialPayment, row.entry_id) is None
            return False

        return None

    @staticmethod
    def _obsolete_reason_for(row: PayableSnapshot) -> str:
        if row.type == PayableSnapshotType.COLLABORATOR:
            return "Colaborador removido da origem (folha/alocação)."
        if row.type == PayableSnapshotType.ANTECIPACAO:
            return "Antecipação/NF removida da origem."
        if row.type == PayableSnapshotType.FIXED_COST:
            obs = row.observation or ""
            if SOURCE_TAG_PROJECT_SYSTEM in obs:
                return "Sistema do projeto removido da origem."
            if SOURCE_TAG_PROJECT_MISC in obs:
                return "Custo diverso do projeto removido da origem."
            return "Custo fixo removido da origem."
        if row.type in PAYABLE_DEBT_TYPES:
            return "Endividamento removido da origem."
        return "Origem removida."

    async def reconcile_snapshot(self, *, month: date, user_id: UUID | None) -> dict:
        """Reconcilia o snapshot do mês: marca como obsoletos os lançamentos
        automáticos cuja origem foi removida; reativa os que voltaram a existir.

        Preserva integralmente histórico financeiro: NÃO altera amount_*,
        pagamentos, estornos nem lançamentos MANUAL.

        Universo avaliado = EXATAMENTE o que a tela do mês exibe
        (`list_for_operational_month`): as obrigações da competência MAIS as linhas de
        outras competências com pagamento no mês. Antes varria só `month == comp`, então
        uma linha visível na tela vinda de outra competência nunca era avaliada — o
        usuário clicava em "Reconciliar" e ela permanecia idêntica. Alinhar o escopo ao
        da tela é o que torna o resultado consistente com o que se vê.

        Ao marcar obsoleto, remove a linha do dashboard (include_in_dashboard=False) para
        não poluir análises — EXCETO quando há pagamento registrado: despesa efetivamente
        paga continua no dashboard (marcada como resíduo, mas nunca some das análises
        financeiras), coerente com "preserva integralmente o histórico financeiro".
        """
        comp = normalize_competencia(month)
        rows = await self.list_for_operational_month(month=comp)
        now = datetime.now(timezone.utc)
        marked = 0
        cleared = 0
        checked = 0
        obsolete_total = 0
        kept_paid_in_dashboard = 0

        for row in rows:
            missing = await self.origin_is_missing(row=row)
            if missing is None:
                # MANUAL, ref_id ausente ou tipo não rastreável: nunca tocar.
                if row.is_obsolete:
                    obsolete_total += 1
                continue
            checked += 1
            if missing:
                if not row.is_obsolete:
                    row.is_obsolete = True
                    row.obsolete_reason = self._obsolete_reason_for(row)
                    row.reconciled_at = now
                    row.reconciled_by = user_id
                    # Só sai do dashboard se NUNCA houve desembolso: despesa paga é fato
                    # financeiro consumado e não pode desaparecer das análises.
                    has_payment = _money2(row.amount_paid) > 0 or await _has_active_payments(
                        self.session, snapshot_id=row.id
                    )
                    if has_payment:
                        kept_paid_in_dashboard += 1
                        logger.warning(
                            "payables reconcile marked obsolete but KEPT in dashboard (has payment) "
                            "snapshot_id=%s name=%s month=%s amount_paid=%s",
                            row.id,
                            row.name,
                            row.month,
                            row.amount_paid,
                        )
                    else:
                        row.include_in_dashboard = False
                    marked += 1
                obsolete_total += 1
            else:
                # Origem reapareceu: reverte a marcação (idempotente e reversível).
                if row.is_obsolete:
                    row.is_obsolete = False
                    row.obsolete_reason = None
                    row.reconciled_at = now
                    row.reconciled_by = user_id
                    row.include_in_dashboard = True
                    cleared += 1

        await self.session.flush()
        logger.info(
            "payables reconcile month=%s rows_in_scope=%d checked=%d marked_obsolete=%d cleared=%d "
            "obsolete_total=%d kept_paid_in_dashboard=%d by=%s",
            comp,
            len(rows),
            checked,
            marked,
            cleared,
            obsolete_total,
            kept_paid_in_dashboard,
            user_id,
        )
        return {
            "month": comp,
            "checked": checked,
            "marked_obsolete": marked,
            "cleared": cleared,
            "obsolete_total": obsolete_total,
        }

    async def can_delete_orphaned_row(self, *, row: PayableSnapshot) -> bool:
        """
        Exclusão segura de linhas órfãs/extornadas no snapshot.

        Regras (libera exclusão mesmo que já tenha existido pagamento no passado):
        - não pode ser ANTECIPACAO
        - não pode estar pago (status derivado != PAGO)
        - amount_paid ativo atual == 0 (pagamentos ativos inexistentes)
        - deve estar órfã (fonte removida) — usa a regra única `origin_is_missing`,
          que cobre COLLABORATOR (colaborador removido), FIXED_COST e
          ENDIVIDAMENTO/FINANCIAL.
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

        return await self.origin_is_missing(row=row) is True

    async def delete_row(self, *, row: PayableSnapshot) -> None:
        await self.session.delete(row)
        await self.session.flush()
