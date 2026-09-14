"""Custos da empresa por competência: cadastro corporativo + Contas a Pagar.

Fonte única usada pelo motor financeiro (Dashboard Operacional) e pelo Resultado da Empresa.

Regra de tempo (aplicada pelo chamador, `FinancialService.company_costs_for_month`): o faturamento
do mês M paga as contas do mês M+1 — então os custos da empresa do mês TRABALHADO M são carregados
aqui pelo mês de PAGAMENTO M+1. Os meses abaixo são sempre meses de pagamento.

Valor de cada item no mês de pagamento:
- Mês FECHADO (anterior ao corrente) e gerado no CAP: o VALOR PAGO dos títulos; o não pago vira
  saldo em aberto (`open_amount`).
- Mês corrente/futuro já gerado: o VALOR FINAL dos títulos (parcial — ainda podem mudar).
- Mês ainda não gerado: projeção pelo cadastro com a MESMA regra da geração
  (`company_finance_rules`), mais os componentes variáveis dos colaboradores.
Nos títulos do CAP ficam de fora os obsoletos e os marcados para não entrar em dashboards.

Destino de cada linha (`split_month`), sempre pelo CADASTRO, nunca pelo nome:
- Item com um PROJETO como centro de custo: custo direto desse projeto, somado na origem raiz
  indicada no item (`project_cost_group`): combustível → Veículos, plano de saúde → Mão de obra…
  (sem indicação → Fixos operacionais).
- FROTA — rateada pelo custo mensal cadastrado dos veículos ativos em cada centro de custo (data de
  aquisição/devolução do cadastro de Veículos); a parte dos projetos é custo de veículos de cada um,
  o resto (Administrativo, Diretoria…) é custo indireto:
  - "Fatura de locação" (ex.: Movida): com título no CAP no mês, vale o VALOR DEVIDO da fatura
    (é obrigação mesmo sem pagamento); sem título, vale o custo mensal total dos veículos ativos.
  - "Custo adicional da frota" (ex.: seguro): rateado do mesmo jeito e SOMADO aos veículos.
- Demais: custo indireto.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import date
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.company_finance import CompanyFinancialItem, CompanyFinancialPayment
from app.models.fleet import Vehicle
from app.models.payable_snapshot import PayableOrigin, PayableSnapshot, PayableSnapshotType
from app.models.payable_snapshot_generation import PayableSnapshotGeneration
from app.models.payment_component import PaymentVariableComponent
from app.models.project import Project
from app.services.company_finance_rules import item_eligible_for_comp, month_bounds, reference_monthly_value
from app.utils.date_utils import normalize_competencia

DEFAULT_INDIRECT_CATEGORY = "Custos diversos"
DEBT_CATEGORY = "Endividamento"
FLEET_CATEGORY = "Frota"
FLEET_RENTAL = "LOCACAO"
FLEET_ADDITIONAL = "ADICIONAL"
# Nome exibido da locação da frota (fatura ou, sem fatura, custo mensal dos veículos ativos).
FLEET_REGISTRY_NAME = "Movida"
PROJECT_GROUP_LABOR = "MAO_DE_OBRA"
PROJECT_GROUP_VEHICLES = "VEICULOS"
PROJECT_GROUP_SYSTEMS = "SISTEMAS"
PROJECT_GROUP_FIXED = "FIXOS"
_PROJECT_GROUPS = (PROJECT_GROUP_LABOR, PROJECT_GROUP_VEHICLES, PROJECT_GROUP_SYSTEMS, PROJECT_GROUP_FIXED)
# Rótulos que o CAP grava na categoria dos títulos gerados (não são categorias do cadastro).
_CAP_LABEL_CATEGORIES = {"Custo Fixo", "Colaborador"}
_EPS = 0.005
# Base dos títulos do CAP pedida pelo chamador (Resultado da Empresa):
# PAGO = só o valor efetivamente pago até agora, em qualquer mês (mês sem títulos = nada pago);
# LANCADO = valor final de tudo o que foi lançado (mês sem títulos = projeção pelo cadastro).
# Sem base (Dashboard Operacional): pago em mês fechado, final no mês em curso, projeção se não gerado.
BASIS_PAID = "PAGO"
BASIS_LAUNCHED = "LANCADO"
# Classificação do lançamento MANUAL do CAP (`payable_snapshots.result_classification`).
MANUAL_RESULT_DIRECT = "DIRETO"  # custo direto do projeto `result_project_id` (entra por load_project_payables)
MANUAL_RESULT_INDIRECT = "INDIRETO"
MANUAL_RESULT_DEBT = "ENDIVIDAMENTO"
MANUAL_RESULT_OUT = "FORA"


@dataclass(frozen=True)
class CostLine:
    """Valor de um item do cadastro corporativo em um mês.

    `amount` é o que entra no resultado (pago, final ou projetado, conforme o mês);
    `open_amount` é o saldo que ficou sem pagar num mês fechado. `project_id` = projeto do centro
    de custo do item; `fleet` = modo de rateio pela frota (None | "LOCACAO" | "ADICIONAL");
    `project_group` = em qual custo do projeto o item soma (None = Fixos operacionais).
    """

    item_id: UUID | None
    name: str
    category: str
    is_labor: bool
    amount: float
    open_amount: float = 0.0
    project_id: UUID | None = None
    fleet: str | None = None
    project_group: str | None = None


@dataclass
class CompanyCostMonth:
    indirect: list[CostLine] = field(default_factory=list)
    debts: list[CostLine] = field(default_factory=list)
    projected: bool = False
    paid_basis: bool = False

    @property
    def partial(self) -> bool:
        """Mês de pagamento em curso: títulos já gerados, valendo o valor final (ainda podem mudar)."""
        return not self.projected and not self.paid_basis


@dataclass(frozen=True)
class FleetMonth:
    """Participação de cada projeto (None = fora dos projetos) e custo mensal total da frota ativa."""

    shares: dict
    registry_total: float


# --------------------------------------------------------------------------- #
# Regras puras
# --------------------------------------------------------------------------- #
def _f(value: object) -> float:
    return float(value or 0)


def indirect_category(item) -> str:
    return str(getattr(item, "category", None) or DEFAULT_INDIRECT_CATEGORY).strip() or DEFAULT_INDIRECT_CATEGORY


def _fleet_mode(item) -> str | None:
    mode = getattr(item, "fleet_allocation", None)
    return mode if mode in (FLEET_RENTAL, FLEET_ADDITIONAL) else None


def project_group_of(line: CostLine) -> str:
    return line.project_group if line.project_group in _PROJECT_GROUPS else PROJECT_GROUP_FIXED


def _item_line(item, *, amount: float, open_amount: float = 0.0, is_labor: bool | None = None) -> CostLine:
    group = getattr(item, "project_cost_group", None)
    return CostLine(
        item.id,
        str(item.nome),
        indirect_category(item),
        item.employee_id is not None if is_labor is None else is_labor,
        amount,
        open_amount,
        getattr(item, "cost_center_project_id", None),
        _fleet_mode(item),
        group if group in _PROJECT_GROUPS else None,
    )


def projected_item_amount(item, *, comp: date, entries_sum: float | None, settings) -> float:
    """Valor do item em um mês AINDA NÃO gerado no CAP — mesma regra da geração.

    `entries_sum` = soma dos lançamentos da grade no mês (None quando não há lançamento).
    Lançamento digitado prevalece (inclusive 0 = "nada neste mês"); sem lançamento, vale a
    referência do item vigente a partir do piso — nunca para cronograma personalizado, que só
    gera título pelas próprias parcelas.
    """
    from app.services.payable_snapshot_service import COMPANY_FINANCE_AUTOGEN_FIRST_COMPETENCE

    if not bool(getattr(item, "is_active", True)):
        return 0.0
    if entries_sum is not None:
        return max(float(entries_sum), 0.0)
    comp = normalize_competencia(comp)
    if comp < COMPANY_FINANCE_AUTOGEN_FIRST_COMPETENCE:
        return 0.0
    if item.tipo == "endividamento" and bool(getattr(item, "uses_custom_schedule", False)):
        return 0.0
    if not item_eligible_for_comp(item, comp):
        return 0.0
    return max(float(reference_monthly_value(item, comp=comp, settings=settings)), 0.0)


def snapshot_amounts(row, *, paid_basis: bool) -> tuple[float, float]:
    """(valor que entra no resultado, saldo em aberto) de um título do CAP."""
    final = _f(row.amount_final)
    if not paid_basis:
        return final, 0.0
    # Sem teto no valor final: pagamento acima do título (juros, multa) também saiu do caixa.
    paid = _f(row.amount_paid)
    return paid, max(final - paid, 0.0)


def line_from_snapshot(
    row, *, items: dict, components: dict, paid_basis: bool = False
) -> tuple[str, CostLine] | None:
    """Classifica um título do CAP (sem projeto) como ("indirect" | "debt", linha) ou None."""
    amount, open_amount = snapshot_amounts(row, paid_basis=paid_basis)
    type_value = getattr(row.type, "value", row.type)
    if type_value == PayableSnapshotType.MANUAL.value:
        # Lançamento avulso: entra só como o financeiro classificou (sem classificação = fora).
        classification = getattr(row, "result_classification", None)
        category = str(row.category or "").strip()
        if classification == MANUAL_RESULT_DEBT:
            return "debt", CostLine(None, str(row.name), DEBT_CATEGORY, False, amount, open_amount)
        if classification == MANUAL_RESULT_INDIRECT:
            return "indirect", CostLine(
                None, str(row.name), category or DEFAULT_INDIRECT_CATEGORY, False, amount, open_amount
            )
        return None
    if type_value in (PayableSnapshotType.ENDIVIDAMENTO.value, PayableSnapshotType.FINANCIAL.value):
        item = items.get(row.ref_id)
        name = str(item.nome) if item is not None else str(row.name)
        return "debt", CostLine(getattr(item, "id", None), name, DEBT_CATEGORY, False, amount, open_amount)
    if type_value != PayableSnapshotType.FIXED_COST.value:
        return None
    origin = row.origin or PayableOrigin.FIXED_COST.value
    if origin == PayableOrigin.VARIABLE.value:
        component = components.get(row.ref_id)
        item = items.get(getattr(component, "company_financial_item_id", None))
        if component is None or item is None:
            return None  # componente de projeto (ou órfão) não é custo da empresa
        return "indirect", _item_line(item, amount=amount, open_amount=open_amount, is_labor=True)
    if origin != PayableOrigin.FIXED_COST.value:
        return None
    item = items.get(row.ref_id)
    if item is not None:
        if item.tipo != "custo_fixo":
            return None
        return "indirect", _item_line(item, amount=amount, open_amount=open_amount)
    # Título legado sem item de origem: usa o que o próprio título diz.
    category = str(row.category or "")
    return "indirect", CostLine(
        None,
        str(row.name),
        DEFAULT_INDIRECT_CATEGORY if category in _CAP_LABEL_CATEGORIES or not category else category,
        category == "Colaborador",
        amount,
        open_amount,
    )


def fleet_for_month(vehicles: Iterable, *, comp: date, project_by_cost_center: dict) -> FleetMonth:
    """Frota ativa no mês pelo cadastro de Veículos (aquisição/devolução), por centro de custo."""
    start, end = month_bounds(comp)
    weights: dict[UUID | None, float] = defaultdict(float)
    for v in vehicles:
        if getattr(v, "deleted_at", None) is not None:
            continue
        if v.start_date is not None and v.start_date > end:
            continue
        if v.end_date is not None and v.end_date < start:
            continue
        if not bool(v.is_active) and v.end_date is None:
            continue
        # Veículo sem centro de custo não está alocado a nada e não entra na frota rateada
        # (ex.: os 16 carros devolvidos em 08/2026 que nunca foram usados — acordo no Endividamento).
        if not (v.cost_center or "").strip():
            continue
        cost = _f(v.monthly_cost)
        if cost <= 0:
            continue
        key = (v.cost_center or "").strip().casefold()
        weights[project_by_cost_center.get(key)] += cost
    total = sum(weights.values())
    shares = {k: w / total for k, w in weights.items()} if total > 0 else {}
    return FleetMonth(shares=shares, registry_total=total)


def _allocate(line: CostLine, shares: dict, indirect: list, projects: dict) -> None:
    project_share = 0.0
    for project_id, share in shares.items():
        if project_id is None:
            continue
        projects[project_id].append(replace(line, amount=line.amount * share, open_amount=line.open_amount * share))
        project_share += share
    rest = 1.0 - project_share
    if rest > 1e-9:
        indirect.append(replace(line, amount=line.amount * rest, open_amount=line.open_amount * rest))


def split_month(
    month: CompanyCostMonth, fleet: FleetMonth, *, rental_due: bool = True, registry_fallback: bool = True
) -> tuple[list[CostLine], dict[UUID, list[CostLine]]]:
    """(linhas indiretas, linhas diretas por projeto) de um mês. Ver docstring do módulo.

    `rental_due=False` mantém a fatura de locação pelo valor da base (pago, com o resto em aberto);
    `registry_fallback=False` não põe o custo dos veículos ativos no lugar da fatura que não existe.
    """
    indirect: list[CostLine] = []
    projects: dict[UUID, list[CostLine]] = defaultdict(list)
    rental_lines: list[CostLine] = []
    for line in month.indirect:
        if line.fleet == FLEET_RENTAL:
            rental_lines.append(line)
        elif line.fleet == FLEET_ADDITIONAL:
            if fleet.shares:
                _allocate(line, fleet.shares, indirect, projects)
            else:
                indirect.append(line)
        elif line.project_id is not None:
            projects[line.project_id].append(line)
        else:
            indirect.append(line)

    has_rental_title = bool(rental_lines) and not month.projected
    if has_rental_title:
        # Valor DEVIDO da fatura: o que não foi pago continua sendo custo da frota.
        rentals = (
            [replace(line, amount=line.amount + line.open_amount, open_amount=0.0) for line in rental_lines]
            if rental_due
            else rental_lines
        )
    elif not registry_fallback:
        rentals = []
    elif fleet.registry_total > _EPS:
        rentals = [CostLine(None, FLEET_REGISTRY_NAME, FLEET_CATEGORY, False, fleet.registry_total, fleet=FLEET_RENTAL)]
    else:
        rentals = rental_lines
    for line in rentals:
        if fleet.shares:
            _allocate(line, fleet.shares, indirect, projects)
        else:
            indirect.append(line)
    return indirect, projects


# --------------------------------------------------------------------------- #
# Carga
# --------------------------------------------------------------------------- #
async def load_company_costs(
    session: AsyncSession,
    months: list[date],
    *,
    settings,
    current_month: date | None = None,
    basis: str | None = None,
) -> dict[date, CompanyCostMonth]:
    out = {normalize_competencia(comp): CompanyCostMonth() for comp in months}
    if not out:
        return out
    months = list(out)
    current = normalize_competencia(current_month or date.today())
    items = {
        it.id: it
        for it in (
            await session.execute(
                select(CompanyFinancialItem)
                .options(selectinload(CompanyFinancialItem.employee))
                .where(CompanyFinancialItem.tipo.in_(("custo_fixo", "endividamento")))
            )
        )
        .scalars()
        .all()
    }
    generated = set(
        (
            await session.execute(
                select(PayableSnapshotGeneration.month).where(PayableSnapshotGeneration.month.in_(months))
            )
        )
        .scalars()
        .all()
    )
    if generated:
        await _load_from_payables(session, out, sorted(generated), items, current_month=current, basis=basis)
    projected = [m for m in months if m not in generated]
    if basis == BASIS_PAID:
        # Mês sem títulos no CAP: nada foi pago.
        for comp in projected:
            out[comp].paid_basis = True
    elif projected:
        await _load_projection(session, out, projected, items, settings=settings)
    return out


@dataclass
class ProjectPayables:
    """Títulos do CAP com projeto num mês de pagamento (folha, sistemas e custos diversos dos projetos)."""

    labor: float = 0.0
    system: float = 0.0
    fixed: float = 0.0
    open_amount: float = 0.0

    @property
    def total(self) -> float:
        return self.labor + self.system + self.fixed


async def load_project_payables(session: AsyncSession, months: list[date], *, basis: str) -> dict[date, ProjectPayables]:
    """Por mês de pagamento: títulos de Colaborador com projeto → mão de obra (inclusive componentes
    variáveis); títulos de sistema do projeto → sistemas; custos diversos do projeto e lançamentos
    manuais classificados como «Custo direto do projeto» → fixos."""
    from app.services.payable_snapshot_service import SOURCE_TAG_PROJECT_SYSTEM

    out = {normalize_competencia(comp): ProjectPayables() for comp in months}
    if not out:
        return out
    rows = (
        (
            await session.execute(
                select(PayableSnapshot).where(
                    PayableSnapshot.month.in_(list(out)),
                    PayableSnapshot.is_obsolete.is_(False),
                    PayableSnapshot.include_in_dashboard.is_(True),
                    or_(
                        and_(
                            PayableSnapshot.project_id.is_not(None),
                            PayableSnapshot.type.in_((PayableSnapshotType.COLLABORATOR, PayableSnapshotType.FIXED_COST)),
                        ),
                        and_(
                            PayableSnapshot.type == PayableSnapshotType.MANUAL,
                            PayableSnapshot.result_classification == MANUAL_RESULT_DIRECT,
                            PayableSnapshot.result_project_id.is_not(None),
                        ),
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        target = out[normalize_competencia(row.month)]
        amount, open_amount = snapshot_amounts(row, paid_basis=basis == BASIS_PAID)
        type_value = getattr(row.type, "value", row.type)
        if type_value == PayableSnapshotType.COLLABORATOR.value:
            target.labor += amount
        elif SOURCE_TAG_PROJECT_SYSTEM in (row.observation or ""):
            target.system += amount
        else:
            target.fixed += amount
        target.open_amount += open_amount
    return out


async def load_fleet(session: AsyncSession, months: list[date]) -> dict[date, FleetMonth]:
    vehicles = (await session.execute(select(Vehicle))).scalars().all()
    project_by_cost_center: dict[str, UUID] = {}
    for project in (await session.execute(select(Project))).scalars().all():
        key = ((getattr(project, "cost_center", None) or "").strip() or (project.name or "").strip()).casefold()
        if key:
            project_by_cost_center.setdefault(key, project.id)
    return {
        normalize_competencia(comp): fleet_for_month(
            vehicles, comp=normalize_competencia(comp), project_by_cost_center=project_by_cost_center
        )
        for comp in months
    }


async def _load_from_payables(
    session, out: dict, months: list[date], items: dict, *, current_month: date, basis: str | None = None
) -> None:
    for comp in months:
        out[comp].paid_basis = basis == BASIS_PAID if basis else comp < current_month
    rows = (
        (
            await session.execute(
                select(PayableSnapshot).where(
                    PayableSnapshot.month.in_(months),
                    PayableSnapshot.project_id.is_(None),
                    PayableSnapshot.is_obsolete.is_(False),
                    PayableSnapshot.include_in_dashboard.is_(True),
                    PayableSnapshot.type.in_(
                        (
                            PayableSnapshotType.FIXED_COST,
                            PayableSnapshotType.ENDIVIDAMENTO,
                            PayableSnapshotType.FINANCIAL,
                            PayableSnapshotType.MANUAL,
                        )
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    variable_ids = [r.ref_id for r in rows if r.origin == PayableOrigin.VARIABLE.value and r.ref_id]
    components = {}
    if variable_ids:
        components = {
            c.id: c
            for c in (
                await session.execute(
                    select(PaymentVariableComponent).where(PaymentVariableComponent.id.in_(variable_ids))
                )
            )
            .scalars()
            .all()
        }
    for row in rows:
        month = out[normalize_competencia(row.month)]
        classified = line_from_snapshot(row, items=items, components=components, paid_basis=month.paid_basis)
        if classified is None:
            continue
        kind, line = classified
        (month.debts if kind == "debt" else month.indirect).append(line)


async def _load_projection(session, out: dict, months: list[date], items: dict, *, settings) -> None:
    entries: dict[tuple[UUID, date], float] = defaultdict(float)
    for item_id, comp, valor in (
        await session.execute(
            select(
                CompanyFinancialPayment.item_id,
                CompanyFinancialPayment.competencia,
                CompanyFinancialPayment.valor,
            ).where(CompanyFinancialPayment.competencia.in_(months))
        )
    ).all():
        entries[(item_id, normalize_competencia(comp))] += _f(valor)
    variables = (
        (
            await session.execute(
                select(PaymentVariableComponent).where(
                    PaymentVariableComponent.competencia.in_(months),
                    PaymentVariableComponent.company_financial_item_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for comp in months:
        month = out[comp]
        month.projected = True
        for item in items.values():
            key = (item.id, comp)
            amount = projected_item_amount(
                item, comp=comp, entries_sum=entries[key] if key in entries else None, settings=settings
            )
            if amount <= _EPS:
                continue
            if item.tipo == "endividamento":
                month.debts.append(CostLine(item.id, str(item.nome), DEBT_CATEGORY, False, amount))
            else:
                month.indirect.append(_item_line(item, amount=amount))
    for component in variables:
        item = items.get(component.company_financial_item_id)
        if item is None or item.tipo != "custo_fixo":
            continue
        out[normalize_competencia(component.competencia)].indirect.append(
            _item_line(item, amount=_f(component.amount), is_labor=True)
        )
