from __future__ import annotations

import calendar
import logging
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.scenario import Scenario, scenario_pg_rhs
from app.models.costs import ProjectFixedCost
from app.models.company_finance import CompanyFinancialItem, CompanyFinancialPayment
from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
from app.models.payable_snapshot_generation import PayableSnapshotGeneration
from app.models.project_operational import ProjectLabor, ProjectOperationalFixed, ProjectVehicle
from app.models.receivable import ReceivableInvoice, ReceivableInvoiceAnticipation
from app.repositories.projects import ProjectRepository
from app.models.project import Project
from app.services.employee_cost_service import project_labor_full_monthly_cost
from app.services.settings_service import SettingsService
from app.utils.date_utils import normalize_competencia, previous_competencia

logger = logging.getLogger(__name__)

PAYABLE_PAYMENT_TOLERANCE = Decimal("0.02")
_MONEY_QUANT = Decimal("0.01")


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


def payable_snapshot_payment_status(*, amount_paid: Decimal, amount_final: Decimal) -> str:
    """ABERTO | PARCIAL | PAGO com base no valor pago acumulado."""
    ap = _money2(amount_paid)
    af = _money2(amount_final)
    if ap <= 0:
        return "ABERTO"
    if ap + PAYABLE_PAYMENT_TOLERANCE < af:
        return "PARCIAL"
    return "PAGO"


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


def _default_due_date(payment_month: date, *, day: int = 10) -> date:
    comp = normalize_competencia(payment_month)
    last = calendar.monthrange(comp.year, comp.month)[1]
    return date(comp.year, comp.month, min(max(day, 1), last))


def _month_bounds(comp: date) -> tuple[date, date]:
    c = normalize_competencia(comp)
    last = calendar.monthrange(c.year, c.month)[1]
    return date(c.year, c.month, 1), date(c.year, c.month, last)


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


def _merge_realizado_previsto(*, real_map: dict, prev_map: dict, key) -> float:
    real = float(real_map.get(key, 0.0) or 0.0)
    prev = float(prev_map.get(key, 0.0) or 0.0)
    return real if real > 0 else prev


class PayableSnapshotService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
            if it.tipo == "custo_fixo":
                if it.id in existing_fixed:
                    continue
                snap_type = PayableSnapshotType.FIXED_COST
                cost_center = "Administrativo"
                category = "Custos diversos"
            else:
                if it.id in existing_fin:
                    continue
                snap_type = PayableSnapshotType.ENDIVIDAMENTO
                cost_center = "Financeiro"
                category = "Endividamento"

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

    def _company_finance_snapshot_meta(self, item: CompanyFinancialItem) -> tuple[PayableSnapshotType, str, str]:
        if item.tipo == "custo_fixo":
            return PayableSnapshotType.FIXED_COST, "Administrativo", "Custos diversos"
        if item.tipo == "endividamento":
            return PayableSnapshotType.ENDIVIDAMENTO, "Financeiro", "Endividamento"
        raise ValueError("Tipo financeiro corporativo inválido para contas a pagar.")

    async def sync_company_finance_item_months(self, *, item_id: UUID, months: set[date]) -> int:
        """
        Sincroniza somente as linhas de payables originadas de um item de Company Finance.

        Não invalida nem recria o snapshot do mês inteiro. Linhas já pagas nunca são apagadas
        e `amount_paid` é preservado ao atualizar valor/vencimento, evitando que histórico pago
        volte para ABERTO por causa de uma edição em outro mês.
        """
        if not months:
            return 0

        item = await self.session.get(CompanyFinancialItem, item_id)
        if item is None:
            return 0
        snap_type, cost_center, category = self._company_finance_snapshot_meta(item)
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
            # Se o snapshot ainda não existe, a geração futura usará company_financial_payments.
            if not await self.is_generated(month=comp):
                continue

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
            amount = payments_by_month.get(comp, Decimal("0.00"))

            if amount <= 0:
                for row in existing:
                    if _money2(row.amount_paid) > 0:
                        _sync_legacy_paid_fields(row)
                        continue
                    await self.session.delete(row)
                    changed += 1
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

            target.name = str(item.nome).strip()
            target.cost_center = cost_center
            target.category = category
            if _money2(target.amount_paid) <= 0:
                target.amount_original = amount
                target.amount_final = amount
                target.due_date = _default_due_date(comp, day=10)
            _sync_legacy_paid_fields(target)

            for row in existing:
                if row.id == target.id:
                    continue
                if _money2(row.amount_paid) > 0:
                    _sync_legacy_paid_fields(row)
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
                    # Bug/estado ruim histórico: marker existe, mas snapshot está vazio. Loga e tenta auto-recuperar.
                    logger.error(
                        "payables snapshot month=%s is marked generated but has 0 rows; will attempt regeneration. "
                        "sees_all=%s accessible_projects=%d source_month=%s",
                        comp,
                        sees_all_projects,
                        project_count,
                        source_month,
                    )
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
                # Auto-recuperação: marker existe mas 0 linhas -> remove marker e tenta gerar novamente.
                logger.error(
                    "payables snapshot month=%s has generation marker but 0 rows; deleting marker and regenerating. "
                    "sees_all=%s accessible_projects=%d source_month=%s",
                    comp,
                    sees_all_projects,
                    project_count,
                    source_month,
                )
                await self.session.execute(
                    text("DELETE FROM payable_snapshot_generations WHERE month = :m"),
                    {"m": comp},
                )
                await self.session.flush()

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

            # --- Collaborators (individual; REALIZADO se existir, senão PREVISTO) ---
            keys_stmt = select(ProjectLabor.project_id, ProjectLabor.employee_id).where(
                ProjectLabor.competencia == source_month,
                ProjectLabor.employee_id.is_not(None),
            )
            if project_filter is not None:
                keys_stmt = keys_stmt.where(ProjectLabor.project_id.in_(sorted(project_filter)))
            keys_stmt = keys_stmt.distinct()
            keys = (await self.session.execute(keys_stmt)).all()

            for project_id, employee_id in keys:
                real = await self._get_labor_row(
                    project_id=project_id,
                    employee_id=employee_id,
                    competencia=source_month,
                    scenario=Scenario.REALIZADO,
                )
                prev = await self._get_labor_row(
                    project_id=project_id,
                    employee_id=employee_id,
                    competencia=source_month,
                    scenario=Scenario.PREVISTO,
                )
                labor_row = real if real is not None else prev
                if labor_row is None:
                    continue

                emp = labor_row.employee
                proj = labor_row.project
                if not emp or not proj:
                    continue

                full = float(project_labor_full_monthly_cost(emp, settings, source_month, labor_row))
                factor = float(labor_row.allocation_percentage or 0) / 100.0
                amount = round(full * factor, 2)
                if amount <= 0:
                    continue

                self.session.add(
                    PayableSnapshot(
                        month=payment_month,
                        type=PayableSnapshotType.COLLABORATOR,
                        ref_id=emp.id,
                        project_id=proj.id,
                        name=_employee_display_name(emp),
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
                if it.tipo == "custo_fixo":
                    snap_type = PayableSnapshotType.FIXED_COST
                    cost_center = "Administrativo"
                    category = "Custos diversos"
                else:
                    snap_type = PayableSnapshotType.ENDIVIDAMENTO
                    cost_center = "Financeiro"
                    category = "Endividamento"
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

            # --- Custos diversos do projeto (operacional + legado), por projeto ---
            fixed_rows = await self._project_fixed_cost_rows(competencia=source_month, project_ids=project_filter)
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
        async def sum_for(scenario: Scenario) -> float:
            stmt = select(func.coalesce(func.sum(ProjectVehicle.monthly_cost), 0)).where(
                ProjectVehicle.competencia == competencia,
                ProjectVehicle.scenario == scenario_pg_rhs(scenario),
            )
            if project_ids is not None:
                stmt = stmt.where(ProjectVehicle.project_id.in_(sorted(project_ids)))
            return float((await self.session.execute(stmt)).scalar_one())

        real = await sum_for(Scenario.REALIZADO)
        if real > 0:
            return real
        return await sum_for(Scenario.PREVISTO)

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

    async def _project_fixed_cost_rows(
        self, *, competencia: date, project_ids: set[UUID] | None
    ) -> list[tuple[UUID, str, float, str, str]]:
        """
        Custos diversos ligados a projeto (operacional + legado), sempre por projeto.

        Retorna tuplas: (project_id, name, amount, cost_center_label, category)
        """
        op_real: dict[tuple[UUID, str], float] = defaultdict(float)
        stmt = (
            select(ProjectOperationalFixed.project_id, ProjectOperationalFixed.name, func.sum(ProjectOperationalFixed.value))
            .where(
                ProjectOperationalFixed.competencia == competencia,
                ProjectOperationalFixed.scenario == scenario_pg_rhs(Scenario.REALIZADO),
            )
        )
        if project_ids is not None:
            stmt = stmt.where(ProjectOperationalFixed.project_id.in_(sorted(project_ids)))
        stmt = stmt.group_by(ProjectOperationalFixed.project_id, ProjectOperationalFixed.name)
        for pid, name, total in (await self.session.execute(stmt)).all():
            base = str(name).strip()
            if not base:
                continue
            op_real[(pid, base)] += float(total or 0.0)

        op_prev: dict[tuple[UUID, str], float] = defaultdict(float)
        stmt = (
            select(ProjectOperationalFixed.project_id, ProjectOperationalFixed.name, func.sum(ProjectOperationalFixed.value))
            .where(
                ProjectOperationalFixed.competencia == competencia,
                ProjectOperationalFixed.scenario == scenario_pg_rhs(Scenario.PREVISTO),
            )
        )
        if project_ids is not None:
            stmt = stmt.where(ProjectOperationalFixed.project_id.in_(sorted(project_ids)))
        stmt = stmt.group_by(ProjectOperationalFixed.project_id, ProjectOperationalFixed.name)
        for pid, name, total in (await self.session.execute(stmt)).all():
            base = str(name).strip()
            if not base:
                continue
            op_prev[(pid, base)] += float(total or 0.0)

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

        leg_prev: dict[tuple[UUID, str], float] = defaultdict(float)
        stmt = (
            select(ProjectFixedCost.project_id, ProjectFixedCost.name, func.sum(ProjectFixedCost.amount_calculated))
            .where(
                ProjectFixedCost.competencia == competencia,
                ProjectFixedCost.scenario == scenario_pg_rhs(Scenario.PREVISTO),
            )
        )
        if project_ids is not None:
            stmt = stmt.where(ProjectFixedCost.project_id.in_(sorted(project_ids)))
        stmt = stmt.group_by(ProjectFixedCost.project_id, ProjectFixedCost.name)
        for pid, name, total in (await self.session.execute(stmt)).all():
            base = str(name).strip()
            if not base:
                continue
            leg_prev[(pid, base)] += float(total or 0.0)

        keys = set(op_real) | set(op_prev) | set(leg_real) | set(leg_prev)
        if not keys:
            return []

        proj_ids = {pid for pid, _ in keys}
        projects = (await self.session.execute(select(Project).where(Project.id.in_(sorted(proj_ids))))).scalars().all()
        proj_map = {p.id: p for p in projects}

        rows: list[tuple[UUID, str, float, str, str]] = []
        for pid, base in sorted(keys, key=lambda t: (str(t[0]), t[1])):
            op_amt = _merge_realizado_previsto(real_map=op_real, prev_map=op_prev, key=(pid, base))
            leg_amt = _merge_realizado_previsto(real_map=leg_real, prev_map=leg_prev, key=(pid, base))
            amount = float(op_amt or 0.0) + float(leg_amt or 0.0)
            if amount <= 0:
                continue

            proj = proj_map.get(pid)
            if proj is None or getattr(proj, "deleted_at", None) is not None:
                continue

            cc = _project_cost_center_label(proj)

            has_op = (pid, base) in op_real or (pid, base) in op_prev
            has_leg = (pid, base) in leg_real or (pid, base) in leg_prev
            if has_op and has_leg:
                category = "Custos diversos"
            elif has_leg:
                category = "Custos diversos (legado)"
            else:
                category = "Custos diversos"

            rows.append((pid, base, amount, cc, category))

        return rows

    async def _validate_manual_cost_center(self, cost_center: str) -> str:
        cc = str(cost_center).strip()
        if not cc:
            raise ValueError("Centro de custo é obrigatório.")
        if cc in MANUAL_PAYABLE_FIXED_COST_CENTERS:
            return cc
        stmt = (
            select(Project.id)
            .where(Project.deleted_at.is_(None), Project.name == cc)
            .limit(1)
        )
        found = (await self.session.execute(stmt)).scalar_one_or_none()
        if found is None:
            raise ValueError(
                "Centro de custo inválido. Use «Administrativo», «Financeiro» ou o nome exato de um projeto cadastrado."
            )
        return cc

    async def create_manual(self, *, month: date, name: str, category: str, cost_center: str, amount: float, due_date: date) -> PayableSnapshot:
        comp = normalize_competencia(month)
        amt = Decimal(str(round(float(amount), 2)))
        cc = await self._validate_manual_cost_center(cost_center)
        row = PayableSnapshot(
            month=comp,
            type=PayableSnapshotType.MANUAL,
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
            observation=None,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def update_row(self, *, row: PayableSnapshot, amount_final: float | None, due_date: date | None, observation: str | None) -> PayableSnapshot:
        if amount_final is not None:
            row.amount_final = Decimal(str(round(float(amount_final), 2)))
            af = _money2(row.amount_final)
            cur_paid = _money2(row.amount_paid)
            if cur_paid > af + PAYABLE_PAYMENT_TOLERANCE:
                row.amount_paid = af
        if due_date is not None:
            row.due_date = due_date
        if observation is not None:
            row.observation = observation
        _sync_legacy_paid_fields(row)
        await self.session.flush()
        return row

    def _append_observation(self, row: PayableSnapshot, line: str) -> None:
        line = line.strip()
        if not line:
            return
        prev = (row.observation or "").strip()
        row.observation = f"{prev}\n{line}".strip() if prev else line

    async def register_payment(
        self, *, row: PayableSnapshot, amount: float, observation: str | None = None
    ) -> PayableSnapshot:
        amt = _money2(amount)
        if amt <= 0:
            raise ValueError("Valor do pagamento deve ser maior que zero.")
        final = _money2(row.amount_final)
        paid_cur = _money2(row.amount_paid)
        remaining = final - paid_cur
        if amt > remaining + PAYABLE_PAYMENT_TOLERANCE:
            raise ValueError("Pagamento excede o saldo (tolerância de centavos).")
        new_paid = paid_cur + amt
        if new_paid > final:
            new_paid = final
        row.amount_paid = new_paid
        anchor = date.today()
        _sync_legacy_paid_fields(row, anchor_date=anchor)
        if observation and observation.strip():
            self._append_observation(row, f"[pagamento +{amt}] {observation.strip()}")
        await self.session.flush()
        return row

    async def reverse_payment(
        self, *, row: PayableSnapshot, amount: float, observation: str | None = None
    ) -> PayableSnapshot:
        amt = _money2(amount)
        if amt <= 0:
            raise ValueError("Valor do estorno deve ser maior que zero.")
        paid_cur = _money2(row.amount_paid)
        new_paid = max(Decimal("0.00"), paid_cur - amt)
        row.amount_paid = new_paid
        _sync_legacy_paid_fields(row)
        if observation and observation.strip():
            self._append_observation(row, f"[estorno -{amt}] {observation.strip()}")
        await self.session.flush()
        return row

    async def delete_row(self, *, row: PayableSnapshot) -> None:
        await self.session.delete(row)
        await self.session.flush()
