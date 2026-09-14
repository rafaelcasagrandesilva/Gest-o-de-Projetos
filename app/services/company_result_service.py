"""Resultado da Empresa: quanto entra pelos projetos e quanto a empresa realmente precisa pagar.

Cascata por competência:

    Receita dos projetos
    − Custos diretos (mão de obra, veículos, sistemas, fixos operacionais —   ┐
      já com os itens dos Custos Indiretos que são do projeto)                │ motor do Dashboard
    − Impostos sobre a receita (pelo regime tributário do mês)                │ Operacional
    − Antecipação (custo real das operações do mês seguinte)                  │ (FinancialService)
    = Lucro operacional                                                       │
    − Retenção 10% (retida pelo cliente, indisponível)                        │
    = Lucro disponível                                                        ┘
    − Custos indiretos (menu Custos Indiretos, sem a parte que é dos projetos)
    − IRPJ/CSLL sobre o lucro (só em mês de Lucro Real; zero no prejuízo)
    − Endividamento (parcelas que vão ao Contas a Pagar)
    = Resultado da empresa

O "Rateio / overhead" (receita × overhead_rate) do motor NÃO entra: aqui os custos indiretos
reais substituem esse percentual — somar os dois contaria a mesma coisa duas vezes.

Regra de tempo: o faturamento do mês M paga as contas do mês M+1 (folha, sistemas, custos dos
projetos, frota, custos indiretos e dívidas vêm dos títulos do CAP de M+1).

Cenários (só nesta tela; o Dashboard Operacional mantém os dele):
- REALIZADO = o que já aconteceu: receita lançada (a mesma do Dashboard Operacional, manual ou
  pelas NFs conforme o Faturamento), impostos devidos sobre ela, antecipação só das operações que
  já ocorreram e TODOS os custos pelo valor PAGO no CAP até agora (o lançado e não pago vai para
  os campos "a pagar"; conta que não está no CAP não entra).
- PREVISTO = simulação: mesma receita (a prevista, se o mês ainda não tem receita realizada),
  antecipação real ou pela média, e todas as contas lançadas no CAP pelo valor final — ou a
  estimativa pelos cadastros quando as contas do mês ainda não foram geradas.

Custos da empresa (destino de cada item): `company_costs`. Tributos: `tax_calc`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scenario import Scenario, coerce_scenario
from app.services.anticipation_rate import SOURCE_MEDIA, SOURCE_PARCIAL, AnticipationRate
from app.services.company_costs import (  # noqa: F401 — reexportados para os testes/consumidores
    BASIS_LAUNCHED,
    BASIS_PAID,
    FLEET_CATEGORY,
    FLEET_REGISTRY_NAME,
    FLEET_RENTAL,
    PROJECT_GROUP_FIXED,
    PROJECT_GROUP_LABOR,
    PROJECT_GROUP_SYSTEMS,
    PROJECT_GROUP_VEHICLES,
    CompanyCostMonth,
    CostLine,
    ProjectPayables,
    line_from_snapshot,
    load_company_costs,
    load_fleet,
    load_project_payables,
    project_group_of,
    projected_item_amount,
    split_month,
)
from app.services.financial_service import FinancialService
from app.services.tax_calc import LUCRO_REAL, profit_taxes_real
from app.utils.date_utils import iter_competencias_inclusive, next_competencia, normalize_competencia

_EPS = 0.005
MIXED_REGIME = "MISTO"

_MONEY_SUM_KEYS = (
    "revenue",
    "direct_cost",
    "labor_cost",
    "vehicle_cost",
    "system_cost",
    "fixed_operational_cost",
    "direct_open_cost",
    "contribution_margin",
    "tax_amount",
    "tax_pis",
    "tax_cofins",
    "tax_iss",
    "tax_irpj",
    "tax_csll",
    "anticipation_amount",
    "operational_profit",
    "retention",
    "available_profit",
    "indirect_cost",
    "indirect_labor_cost",
    "indirect_supplier_cost",
    "indirect_open_cost",
    "profit_tax_amount",
    "debt_cost",
    "debt_open_cost",
    "company_result",
)
_FLAG_KEYS = (
    "anticipation_partial",
    "indirect_projected",
    "debt_projected",
    "company_costs_partial",
    "paid_basis",
    "labor_real",
    "vehicle_real",
)


def _f(value: object) -> float:
    return float(value or 0)


def build_month(
    *,
    competencia: date | None,
    cons: dict,
    indirect: list[CostLine],
    costs: CompanyCostMonth,
    settings=None,
) -> dict:
    """Uma linha da cascata a partir do consolidado dos projetos + custos da empresa.

    `indirect` = linhas que ficaram indiretas depois de `split_month` (a parte dos projetos já está
    dentro do consolidado).
    """
    revenue = _f(cons.get("revenue_total"))
    direct = _f(cons.get("operational_cost"))
    tax = _f(cons.get("tax_amount"))
    anticipation = _f(cons.get("anticipation_amount"))
    retention = _f(cons.get("total_retention"))
    operational_profit = revenue - direct - tax - anticipation
    available = operational_profit - retention
    indirect_cost = sum(line.amount for line in indirect)
    indirect_labor = sum(line.amount for line in indirect if line.is_labor)
    debt = sum(line.amount for line in costs.debts)
    regime = cons.get("tax_regime")
    profit_tax = 0.0
    if regime == LUCRO_REAL:
        # Base aproximada do lucro tributável: lucro operacional (a retenção continua sendo receita)
        # menos os custos indiretos. Parcelas de dívida são amortização, não despesa.
        irpj, csll = profit_taxes_real(settings=settings, taxable_profit=operational_profit - indirect_cost)
        profit_tax = irpj + csll
    row = {
        "competencia": competencia,
        "revenue": revenue,
        "direct_cost": direct,
        "labor_cost": _f(cons.get("labor_cost")),
        "vehicle_cost": _f(cons.get("vehicle_cost")),
        "system_cost": _f(cons.get("system_cost")),
        "fixed_operational_cost": _f(cons.get("fixed_operational_cost")),
        "labor_real": bool(cons.get("labor_real")),
        "vehicle_real": bool(cons.get("vehicle_real")),
        "direct_open_cost": _f(cons.get("direct_open_cost")),
        "contribution_margin": revenue - direct,
        "tax_regime": regime,
        "tax_amount": tax,
        "tax_pis": _f(cons.get("tax_pis")),
        "tax_cofins": _f(cons.get("tax_cofins")),
        "tax_iss": _f(cons.get("tax_iss")),
        "tax_irpj": _f(cons.get("tax_irpj")),
        "tax_csll": _f(cons.get("tax_csll")),
        "anticipation_amount": anticipation,
        "anticipation_partial": bool(cons.get("anticipation_partial")),
        "anticipation_by_institution": {k: _f(v) for k, v in (cons.get("anticipation_by_institution") or {}).items()},
        "operational_profit": operational_profit,
        "retention": retention,
        "available_profit": available,
        "indirect_cost": indirect_cost,
        "indirect_labor_cost": indirect_labor,
        "indirect_supplier_cost": indirect_cost - indirect_labor,
        "indirect_open_cost": sum(line.open_amount for line in indirect),
        "indirect_projected": costs.projected,
        "profit_tax_amount": profit_tax,
        "debt_cost": debt,
        "debt_open_cost": sum(line.open_amount for line in costs.debts),
        "debt_projected": costs.projected,
        "paid_basis": costs.paid_basis,
        "company_costs_partial": bool(cons.get("company_costs_partial", costs.partial)),
        "company_result": available - indirect_cost - profit_tax - debt,
    }
    return with_ratios(row)


def with_ratios(row: dict) -> dict:
    """Percentuais sempre recalculados sobre os valores da própria linha (mês ou período)."""
    revenue = row["revenue"]
    available = row["available_profit"]
    burden = row["indirect_cost"] + row["profit_tax_amount"] + row["debt_cost"]
    has_revenue = revenue > _EPS
    row["anticipation_rate"] = row["anticipation_amount"] / revenue if has_revenue else None
    row["tax_rate"] = row["tax_amount"] / revenue if has_revenue else None
    row["available_margin"] = available / revenue if has_revenue else None
    # Margem necessária: quanto da receita teria que sobrar (lucro disponível) para pagar os custos
    # da empresa — indiretos, IRPJ/CSLL e dívidas — e fechar em zero.
    row["required_margin"] = burden / revenue if has_revenue else None
    row["coverage"] = available / burden if burden > _EPS else None
    # Faturamento para fechar 0 a 0 (existe também com resultado negativo): os custos que NÃO crescem
    # com a receita (diretos, indiretos, dívidas) ÷ o que sobra de cada real faturado depois do que
    # cresce com ela (impostos, antecipação e retenção, nas taxas efetivas do mês/período).
    # IRPJ/CSLL do Lucro Real incidem sobre o lucro — no zero a zero não há lucro, então não entram.
    variable_share = (row["tax_amount"] + row["anticipation_amount"] + row["retention"]) / revenue if has_revenue else None
    fixed_costs = row["direct_cost"] + row["indirect_cost"] + row["debt_cost"]
    if variable_share is not None and variable_share < 1 - _EPS and fixed_costs > _EPS:
        row["break_even_revenue"] = fixed_costs / (1 - variable_share)
        row["revenue_gap"] = row["break_even_revenue"] - revenue
    else:
        row["break_even_revenue"] = None
        row["revenue_gap"] = None
    return row


def aggregate_months(rows: list[dict]) -> dict:
    total = {key: sum(r[key] for r in rows) for key in _MONEY_SUM_KEYS}
    for key in _FLAG_KEYS:
        total[key] = any(r[key] for r in rows)
    by_institution: dict[str, float] = defaultdict(float)
    for r in rows:
        for name, value in (r.get("anticipation_by_institution") or {}).items():
            by_institution[name] += value
    total["anticipation_by_institution"] = dict(by_institution)
    regimes = {r["tax_regime"] for r in rows}
    total["tax_regime"] = regimes.pop() if len(regimes) == 1 else MIXED_REGIME
    total["competencia"] = None
    return with_ratios(total)


def summarize_lines(
    months: Iterable[tuple[list[CostLine], CompanyCostMonth]],
) -> tuple[list[dict], list[dict], list[dict]]:
    """(indiretos por categoria, indiretos por item, dívidas por item) no período, desc."""
    by_category: dict[str, float] = defaultdict(float)
    by_item: dict[tuple, dict] = {}
    debts: dict[tuple, dict] = {}
    for indirect, month in months:
        for line in indirect:
            by_category[line.category] += line.amount
            if line.fleet == FLEET_RENTAL:
                # Locação da frota numa linha só, venha da fatura do CAP ou do cadastro de veículos.
                key = ("fleet-rental",)
                seed = {"item_id": None, "name": FLEET_REGISTRY_NAME, "category": FLEET_CATEGORY}
            else:
                key = (line.item_id, line.name if line.item_id is None else None)
                seed = {"item_id": line.item_id, "name": line.name, "category": line.category}
            entry = by_item.setdefault(key, {**seed, "is_labor": False, "amount": 0.0})
            entry["amount"] += line.amount
            entry["is_labor"] = entry["is_labor"] or line.is_labor
        for line in month.debts:
            key = (line.item_id, line.name if line.item_id is None else None)
            entry = debts.setdefault(key, {"item_id": line.item_id, "name": line.name, "amount": 0.0})
            entry["amount"] += line.amount

    def _desc(values: Iterable[dict]) -> list[dict]:
        return sorted((v for v in values if abs(v["amount"]) > _EPS), key=lambda v: -v["amount"])

    categories = _desc({"category": c, "amount": a} for c, a in by_category.items())
    return categories, _desc(by_item.values()), _desc(debts.values())


class CompanyResultService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.financial = FinancialService(session)

    async def company_result(
        self, *, start: date, end: date, scenario: str | Scenario, current_month: date | None = None
    ) -> dict:
        sc = coerce_scenario(scenario)
        basis = BASIS_PAID if sc == Scenario.REALIZADO else BASIS_LAUNCHED
        current = normalize_competencia(current_month or date.today())
        months = iter_competencias_inclusive(normalize_competencia(start), normalize_competencia(end))
        pay_months = [next_competencia(comp) for comp in months]
        settings = await self.financial.get_settings_row()
        company = await load_company_costs(self.session, pay_months, settings=settings, basis=basis)
        project_titles = await load_project_payables(self.session, pay_months, basis=basis)
        fleets = await load_fleet(self.session, months)
        rows = []
        split_months = []
        for comp, pay_month in zip(months, pay_months):
            costs = company[pay_month]
            # Frota: no REALIZADO só a fatura paga (sem fatura, nada); no PREVISTO a fatura lançada ou,
            # sem ela, o custo mensal dos veículos ativos.
            indirect, by_project = split_month(
                costs, fleets[comp], rental_due=False, registry_fallback=basis == BASIS_LAUNCHED
            )
            cons = await self._projects_month(
                comp, sc, settings=settings, costs=costs, titles=project_titles[pay_month], by_project=by_project
            )
            cons["company_costs_partial"] = sc == Scenario.REALIZADO and pay_month >= current
            rows.append(build_month(competencia=comp, cons=cons, indirect=indirect, costs=costs, settings=settings))
            split_months.append((indirect, costs))
        categories, items, debts = summarize_lines(split_months)
        return {
            "scenario": sc.value,
            "basis": basis,
            "period_start": months[0],
            "period_end": months[-1],
            "month_count": len(months),
            "totals": aggregate_months(rows),
            "months": rows,
            "indirect_by_category": categories,
            "indirect_items": items,
            "debt_items": debts,
        }

    async def _projects_month(
        self,
        comp: date,
        sc: Scenario,
        *,
        settings,
        costs: CompanyCostMonth,
        titles: ProjectPayables,
        by_project: dict,
    ) -> dict:
        """Receita, tributos, antecipação e custos diretos do mês trabalhado, no formato do consolidado."""
        fin = self.financial
        revenue_sc = Scenario.REALIZADO
        revenue = await fin.calcular_receita_total(project_id=None, competencia=comp, scenario=revenue_sc)
        if sc == Scenario.PREVISTO and revenue <= _EPS:
            # Mês ainda sem receita realizada: a simulação usa a receita prevista.
            revenue_sc = Scenario.PREVISTO
            revenue = await fin.calcular_receita_total(project_id=None, competencia=comp, scenario=revenue_sc)
        retention = await fin.calcular_total_retencao(project_id=None, competencia=comp, scenario=revenue_sc)
        taxes = await fin.impostos_receita(receita=revenue, competencia=comp, scenario=revenue_sc)
        rate = await fin.taxa_antecipacao(settings=settings, competencia=comp, scenario=Scenario.REALIZADO)
        if sc == Scenario.REALIZADO and rate.source == SOURCE_MEDIA:
            # Sem operação de antecipação ainda: no realizado não há custo (a média é só estimativa).
            rate = AnticipationRate(0.0, rate.source)
        anticipation = revenue * rate.rate

        lines = [line for project_lines in by_project.values() for line in project_lines]
        if costs.projected:
            # Contas do mês de pagamento ainda não geradas (só no PREVISTO): estimativa pelos cadastros.
            parts = await fin.calcular_operacional_estruturado(project_id=None, competencia=comp, scenario=revenue_sc)
            labor, vehicle = parts["labor_cost"], parts["vehicle_cost"]
            system, fixed = parts["system_cost"], parts["fixed_operational_cost"]
            direct_open = 0.0
        else:
            groups: dict[str, float] = defaultdict(float)
            fleet = 0.0
            for line in lines:
                if line.fleet:
                    fleet += line.amount
                else:
                    groups[project_group_of(line)] += line.amount
            labor = titles.labor + groups[PROJECT_GROUP_LABOR]
            vehicle = fleet + groups[PROJECT_GROUP_VEHICLES]
            system = titles.system + groups[PROJECT_GROUP_SYSTEMS]
            fixed = titles.fixed + groups[PROJECT_GROUP_FIXED]
            direct_open = titles.open_amount + sum(line.open_amount for line in lines)
        return {
            "revenue_total": revenue,
            "total_retention": retention,
            "labor_cost": labor,
            "vehicle_cost": vehicle,
            "system_cost": system,
            "fixed_operational_cost": fixed,
            "operational_cost": labor + vehicle + system + fixed,
            "direct_open_cost": direct_open,
            "tax_amount": taxes.total,
            "tax_regime": taxes.regime,
            "tax_pis": taxes.pis,
            "tax_cofins": taxes.cofins,
            "tax_iss": taxes.iss,
            "tax_irpj": taxes.irpj,
            "tax_csll": taxes.csll,
            "anticipation_amount": anticipation,
            "anticipation_partial": rate.source == SOURCE_PARCIAL,
            "anticipation_by_institution": {name: anticipation * share for name, share in rate.split},
        }
