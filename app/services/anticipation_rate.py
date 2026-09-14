"""Custo de antecipação no motor financeiro: a taxa efetiva de cada competência.

O motor aplica `receita × taxa` (total e por projeto — o custo é repartido entre os projetos
proporcionalmente à receita). Esta é a fonte ÚNICA da taxa, usada pelo Dashboard Operacional e
por tudo que consome o motor.

Por que um mês À FRENTE: a M&E trabalha no mês M e só antecipa em M+1 — primeiro na Lepta
(dinheiro novo para pagar a operação), depois na Daycoval (que liquida as operações vencidas da
Lepta). Não se sabe de antemão quais NFs serão antecipadas, então a pergunta é "quanto do
dinheiro que vai entrar pelo trabalho de M sai em taxas de antecipação?" — e a resposta é o custo
das operações de M+1, Lepta + Daycoval.

Modo FIXO: `settings.anticipation_rate`, como sempre foi.

Modo AUTOMATICO (padrão), para a competência M:
- REALIZADO e M+1 já teve operações: custo REAL das operações de M+1 ÷ receita realizada de M.
  Enquanto M+1 é o mês corrente, o valor ainda pode subir → fonte PARCIAL.
- REALIZADO e M+1 já terminou sem nenhuma operação (depois da primeira antecipação): 0.
- M+1 é o mês corrente e ainda não houve operação, M+1 no futuro, ou cenário PREVISTO: média
  PONDERADA dos pares já fechados (Σ custo de m+1 ÷ Σ receita de m, m anterior a M).
- Sem histórico: cai no percentual fixo.

Divisão por instituição (`split`): a participação de cada instituição no custo usado — as operações
de M+1 (REAL/PARCIAL) ou os pares da média (MEDIA). No percentual fixo não há divisão.

Custo real de uma operação = valor cedido − valor creditado, pela data da operação
(`receive_date`), só operações confirmadas (OPEN/SETTLED), todas as instituições. O REPASSE
(Lepta) NÃO entra: é saldo guardado na instituição para liquidar dívida, não taxa.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.scenario import Scenario, coerce_scenario
from app.models.receivable_advance_batch import CONFIRMED_BATCH_STATUSES, ReceivableAdvanceBatch
from app.utils.date_utils import next_competencia, normalize_competencia, previous_competencia

MODE_AUTOMATICO = "AUTOMATICO"
MODE_FIXO = "FIXO"

SOURCE_REAL = "REAL"
SOURCE_PARCIAL = "PARCIAL"
SOURCE_MEDIA = "MEDIA"
SOURCE_FIXA = "FIXA"

UNKNOWN_INSTITUTION = "Sem instituição"
_EPS = 0.005


@dataclass(frozen=True)
class AnticipationRate:
    rate: float  # fração 0–1 aplicada sobre a receita
    source: str  # REAL | PARCIAL | MEDIA | FIXA
    split: tuple[tuple[str, float], ...] = ()  # (instituição, fração do custo), desc


def batch_advanced_and_cost(batch) -> tuple[float, float | None]:
    """(valor cedido, custo financeiro) de UMA operação — a mesma conta da tela de Antecipações.

    Cedido = Σ `advanced_amount` das NFs; operações antigas sem esse dado caem em
    recebido + deságio + tarifas. Custo = cedido − recebido (None quando não há base).
    O repasse não participa.
    """
    total = 0.0
    has_advanced = False
    for item in batch.items or []:
        if getattr(item, "advanced_amount", None) is not None:
            total += float(item.advanced_amount or 0)
            has_advanced = True
    advanced = round(
        total
        if has_advanced
        else float(batch.received_amount or 0) + float(batch.discount_amount or 0) + float(batch.fee_amount or 0),
        2,
    )
    if advanced <= _EPS:
        return advanced, None
    return advanced, advanced - float(batch.received_amount or 0)


def _fractions(costs: Mapping[str, float]) -> tuple[tuple[str, float], ...]:
    positive = {k: float(v) for k, v in costs.items() if float(v) > _EPS}
    total = sum(positive.values())
    if total <= _EPS:
        return ()
    return tuple(sorted(((k, v / total) for k, v in positive.items()), key=lambda kv: -kv[1]))


def resolve_anticipation_rate(
    *,
    mode: str,
    fixed_rate: float,
    competencia: date,
    scenario: str | Scenario,
    current_month: date,
    monthly_cost: Mapping[date, float],
    monthly_revenue: Mapping[date, float],
    cost_by_institution: Mapping[date, Mapping[str, float]] | None = None,
) -> AnticipationRate:
    """Regra pura (sem banco). `monthly_cost` por mês da OPERAÇÃO; `monthly_revenue` por mês
    TRABALHADO; `cost_by_institution` (opcional) = custo do mês da operação por instituição."""
    comp = normalize_competencia(competencia)
    current = normalize_competencia(current_month)
    by_inst = {normalize_competencia(m): v for m, v in (cost_by_institution or {}).items()}
    if mode != MODE_AUTOMATICO:
        return AnticipationRate(float(fixed_rate), SOURCE_FIXA)

    paid = {normalize_competencia(m): float(c) for m, c in monthly_cost.items() if float(c) > _EPS}
    op_month = next_competencia(comp)
    if coerce_scenario(scenario) == Scenario.REALIZADO and paid and min(paid) <= op_month <= current:
        has_operation = op_month in paid
        # Mês das operações ainda em curso e sem nenhuma: usa a média em vez de cravar zero.
        if has_operation or op_month < current:
            revenue = float(monthly_revenue.get(comp, 0) or 0)
            if revenue > _EPS:
                source = SOURCE_PARCIAL if op_month == current else SOURCE_REAL
                return AnticipationRate(
                    paid.get(op_month, 0.0) / revenue, source, _fractions(by_inst.get(op_month, {}))
                )

    cost_sum = revenue_sum = 0.0
    inst_sum: dict[str, float] = defaultdict(float)
    for month_op, cost in paid.items():
        worked = previous_competencia(month_op)
        # Só pares fechados (mês das operações já terminou) e anteriores à competência.
        if worked >= comp or month_op >= current:
            continue
        revenue = float(monthly_revenue.get(worked, 0) or 0)
        if revenue > _EPS:
            cost_sum += cost
            revenue_sum += revenue
            for inst, value in by_inst.get(month_op, {}).items():
                inst_sum[inst] += float(value)
    if revenue_sum > _EPS:
        return AnticipationRate(cost_sum / revenue_sum, SOURCE_MEDIA, _fractions(inst_sum))
    return AnticipationRate(float(fixed_rate), SOURCE_FIXA)


class AnticipationRateResolver:
    """Carrega o custo real por mês (uma query) e a receita dos meses necessários (com cache)."""

    def __init__(self, session: AsyncSession, revenue_of: Callable[[date], Awaitable[float]]):
        self.session = session
        self._revenue_of = revenue_of
        self._costs: dict[date, float] | None = None
        self._costs_by_institution: dict[date, dict[str, float]] = {}
        self._revenue: dict[date, float] = {}
        self._rates: dict[tuple, AnticipationRate] = {}

    async def monthly_costs(self) -> dict[date, float]:
        """Custo real das antecipações por mês da OPERAÇÃO (Lepta + Daycoval, sem repasse)."""
        if self._costs is None:
            batches = (
                (
                    await self.session.execute(
                        select(ReceivableAdvanceBatch)
                        .options(selectinload(ReceivableAdvanceBatch.items))
                        .where(ReceivableAdvanceBatch.status.in_(CONFIRMED_BATCH_STATUSES))
                    )
                )
                .scalars()
                .all()
            )
            costs: dict[date, float] = {}
            by_inst: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
            for batch in batches:
                _, cost = batch_advanced_and_cost(batch)
                if cost is None or cost <= 0:
                    continue
                month = normalize_competencia(batch.receive_date)
                costs[month] = costs.get(month, 0.0) + cost
                by_inst[month][(batch.institution or "").strip() or UNKNOWN_INSTITUTION] += cost
            self._costs = costs
            self._costs_by_institution = {m: dict(v) for m, v in by_inst.items()}
        return self._costs

    async def _revenue_for(self, month: date) -> float:
        if month not in self._revenue:
            self._revenue[month] = float(await self._revenue_of(month) or 0)
        return self._revenue[month]

    async def resolve(self, *, settings, competencia: date, scenario: str | Scenario) -> AnticipationRate:
        comp = normalize_competencia(competencia)
        sc = coerce_scenario(scenario)
        mode = getattr(settings, "anticipation_mode", None) or MODE_AUTOMATICO
        fixed = float(getattr(settings, "anticipation_rate", 0) or 0)
        key = (mode, fixed, comp, sc)
        if key in self._rates:
            return self._rates[key]
        if mode != MODE_AUTOMATICO:
            result = AnticipationRate(fixed, SOURCE_FIXA)
        else:
            costs = await self.monthly_costs()
            worked_months = {previous_competencia(m) for m in costs}
            months = {comp} | {m for m in worked_months if m < comp}
            revenue = {m: await self._revenue_for(m) for m in months}
            result = resolve_anticipation_rate(
                mode=mode,
                fixed_rate=fixed,
                competencia=comp,
                scenario=sc,
                current_month=date.today().replace(day=1),
                monthly_cost=costs,
                monthly_revenue=revenue,
                cost_by_institution=self._costs_by_institution,
            )
        self._rates[key] = result
        return result
