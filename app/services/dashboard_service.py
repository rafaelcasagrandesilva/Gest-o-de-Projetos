from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scenario import DEFAULT_SCENARIO, Scenario, coerce_scenario
from app.models.dashboard import KPI
from app.models.project import Project
from app.services.financial_service import FinancialService, custo_percentual_receita
from app.utils.date_utils import (
    iter_competencias_inclusive,
    normalize_competencia,
    period_last_n_months,
)


def _last_n_month_first_days(n: int) -> list[date]:
    today = date.today()
    y, m = today.year, today.month
    months: list[date] = []
    for _ in range(n):
        months.append(date(y, m, 1))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(months))


def _consolidado_to_monthly_row(comp: date, cons: dict) -> dict:
    return {
        "competencia": comp,
        "revenue_total": cons["revenue_total"],
        "total_revenue": cons["total_revenue"],
        "cost_total": cons["total_cost"],
        "total_cost": cons["total_cost"],
        "total_retention": cons["total_retention"],
        "operational_profit": cons["operational_profit"],
        "net_profit": cons["net_profit"],
        "margin_operational": cons["margin_operational"],
        "margin_net": cons["margin_net"],
        "ebitda": cons["ebitda"],
        "ebitda_margin": cons["ebitda_margin"],
        "profit": cons["profit"],
        "margin": cons["margin"],
        "operational_cost": cons["operational_cost"],
        "tax_amount": cons["tax_amount"],
        "overhead_amount": cons["overhead_amount"],
        "anticipation_amount": cons["anticipation_amount"],
        "labor_cost_pct": cons["labor_cost_pct"],
        "vehicle_cost_pct": cons["vehicle_cost_pct"],
        "system_cost_pct": cons["system_cost_pct"],
        "fixed_operational_cost_pct": cons["fixed_operational_cost_pct"],
        "operational_cost_pct": cons["operational_cost_pct"],
        "tax_amount_pct": cons["tax_amount_pct"],
        "overhead_amount_pct": cons["overhead_amount_pct"],
        "anticipation_amount_pct": cons["anticipation_amount_pct"],
    }


def _aggregate_summary_dicts(rows: list[dict]) -> dict:
    """Soma meses; margens e % recalculados sobre totais do período."""
    if not rows:
        raise ValueError("rows vazio")
    keys_sum = (
        "revenue_total",
        "total_revenue",
        "total_retention",
        "operational_cost",
        "labor_cost",
        "vehicle_cost",
        "system_cost",
        "fixed_operational_cost",
        "tax_amount",
        "overhead_amount",
        "anticipation_amount",
        "total_cost",
        "operational_profit",
        "net_profit",
        "ebitda",
    )
    acc: dict[str, float] = {k: 0.0 for k in keys_sum}
    for r in rows:
        for k in keys_sum:
            acc[k] += float(r.get(k, 0) or 0)
    rev = acc["total_revenue"]
    p = custo_percentual_receita
    margin_operational = 0.0 if rev == 0 else float(acc["operational_profit"] / rev)
    margin_net = 0.0 if rev == 0 else float(acc["net_profit"] / rev)
    ebitda_margin = 0.0 if rev == 0 else float(acc["ebitda"] / rev)
    base = {
        "revenue_total": acc["revenue_total"],
        "total_revenue": acc["total_revenue"],
        "total_retention": acc["total_retention"],
        "operational_cost": acc["operational_cost"],
        "labor_cost": acc["labor_cost"],
        "vehicle_cost": acc["vehicle_cost"],
        "system_cost": acc["system_cost"],
        "fixed_operational_cost": acc["fixed_operational_cost"],
        "tax_amount": acc["tax_amount"],
        "overhead_amount": acc["overhead_amount"],
        "anticipation_amount": acc["anticipation_amount"],
        "total_cost": acc["total_cost"],
        "cost_total": acc["total_cost"],
        "operational_profit": acc["operational_profit"],
        "net_profit": acc["net_profit"],
        "margin_operational": margin_operational,
        "margin_net": margin_net,
        "ebitda": acc["ebitda"],
        "ebitda_margin": ebitda_margin,
        "profit": acc["operational_profit"],
        "margin": margin_operational,
        "labor_cost_pct": p(acc["labor_cost"], rev),
        "vehicle_cost_pct": p(acc["vehicle_cost"], rev),
        "system_cost_pct": p(acc["system_cost"], rev),
        "fixed_operational_cost_pct": p(acc["fixed_operational_cost"], rev),
        "operational_cost_pct": p(acc["operational_cost"], rev),
        "tax_amount_pct": p(acc["tax_amount"], rev),
        "overhead_amount_pct": p(acc["overhead_amount"], rev),
        "anticipation_amount_pct": p(acc["anticipation_amount"], rev),
    }
    base["project_id"] = rows[0].get("project_id")
    base["competencia"] = rows[-1]["competencia"]
    return base


class DashboardService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.financial = FinancialService(session)

    async def resumo_period(
        self,
        *,
        project_id: UUID | None,
        start: date,
        end: date,
        scenario: str | Scenario = DEFAULT_SCENARIO,
    ) -> dict:
        sc = coerce_scenario(scenario)
        await self.financial.warn_if_legacy_project_costs_exist()
        month_rows: list[dict] = []
        for comp in iter_competencias_inclusive(start, end):
            if project_id is not None:
                month_rows.append(
                    await self.resumo_por_projeto(project_id=project_id, competencia=comp, scenario=sc)
                )
            else:
                month_rows.append(await self.resumo_geral_diretor(competencia=comp, scenario=sc))
        return _aggregate_summary_dicts(month_rows)

    async def serie_mensal_interval(
        self,
        *,
        project_id: UUID | None,
        start: date,
        end: date,
        scenario: str | Scenario = DEFAULT_SCENARIO,
    ) -> list[dict]:
        sc = coerce_scenario(scenario)
        out: list[dict] = []
        for comp in iter_competencias_inclusive(start, end):
            if project_id is not None:
                cons = await self.financial.calcular_consolidado_projeto(
                    project_id=project_id, competencia=comp, scenario=sc
                )
            else:
                cons = await self.financial.calcular_consolidado_global(competencia=comp, scenario=sc)
            out.append(_consolidado_to_monthly_row(comp, cons))
        return out

    async def lucro_liquido_previsto_e_realizado_period(
        self,
        *,
        project_id: UUID | None,
        start: date,
        end: date,
    ) -> tuple[float, float]:
        prev_total = 0.0
        real_total = 0.0
        for comp in iter_competencias_inclusive(start, end):
            if project_id is not None:
                p = await self.resumo_por_projeto(
                    project_id=project_id, competencia=comp, scenario=Scenario.PREVISTO
                )
                r = await self.resumo_por_projeto(
                    project_id=project_id, competencia=comp, scenario=Scenario.REALIZADO
                )
            else:
                p = await self.resumo_geral_diretor(competencia=comp, scenario=Scenario.PREVISTO)
                r = await self.resumo_geral_diretor(competencia=comp, scenario=Scenario.REALIZADO)
            prev_total += float(p["net_profit"])
            real_total += float(r["net_profit"])
        return prev_total, real_total

    async def lucro_liquido_previsto_e_realizado(
        self,
        *,
        project_id: UUID | None,
        competencia: date,
        summary_for_requested_scenario: dict,
        requested_scenario: Scenario,
    ) -> tuple[float, float]:
        """Par (previsto, realizado) de `net_profit`; no máximo um `resumo_*` extra além do já calculado."""
        if requested_scenario == Scenario.PREVISTO:
            net_prev = float(summary_for_requested_scenario["net_profit"])
            if project_id is None:
                other = await self.resumo_geral_diretor(competencia=competencia, scenario=Scenario.REALIZADO)
            else:
                other = await self.resumo_por_projeto(
                    project_id=project_id, competencia=competencia, scenario=Scenario.REALIZADO
                )
            return net_prev, float(other["net_profit"])
        net_real = float(summary_for_requested_scenario["net_profit"])
        if project_id is None:
            other = await self.resumo_geral_diretor(competencia=competencia, scenario=Scenario.PREVISTO)
        else:
            other = await self.resumo_por_projeto(
                project_id=project_id, competencia=competencia, scenario=Scenario.PREVISTO
            )
        return float(other["net_profit"]), net_real

    async def resumo_por_projeto(
        self, *, project_id: UUID, competencia: date, scenario: str | Scenario = DEFAULT_SCENARIO
    ) -> dict:
        sc = coerce_scenario(scenario)
        await self.financial.warn_if_legacy_project_costs_exist()
        cons = await self.financial.calcular_consolidado_projeto(
            project_id=project_id, competencia=competencia, scenario=sc
        )
        return {
            "project_id": project_id,
            "competencia": competencia,
            "revenue_total": cons["revenue_total"],
            "total_revenue": cons["total_revenue"],
            "cost_total": cons["total_cost"],
            "total_cost": cons["total_cost"],
            "total_retention": cons["total_retention"],
            "operational_profit": cons["operational_profit"],
            "net_profit": cons["net_profit"],
            "margin_operational": cons["margin_operational"],
            "margin_net": cons["margin_net"],
            "ebitda": cons["ebitda"],
            "ebitda_margin": cons["ebitda_margin"],
            "profit": cons["profit"],
            "margin": cons["margin"],
            "operational_cost": cons["operational_cost"],
            "labor_cost": cons["labor_cost"],
            "vehicle_cost": cons["vehicle_cost"],
            "system_cost": cons["system_cost"],
            "fixed_operational_cost": cons["fixed_operational_cost"],
            "tax_amount": cons["tax_amount"],
            "overhead_amount": cons["overhead_amount"],
            "anticipation_amount": cons["anticipation_amount"],
            "labor_cost_pct": cons["labor_cost_pct"],
            "vehicle_cost_pct": cons["vehicle_cost_pct"],
            "system_cost_pct": cons["system_cost_pct"],
            "fixed_operational_cost_pct": cons["fixed_operational_cost_pct"],
            "operational_cost_pct": cons["operational_cost_pct"],
            "tax_amount_pct": cons["tax_amount_pct"],
            "overhead_amount_pct": cons["overhead_amount_pct"],
            "anticipation_amount_pct": cons["anticipation_amount_pct"],
        }

    async def resumo_geral_diretor(self, *, competencia: date, scenario: str | Scenario = DEFAULT_SCENARIO) -> dict:
        sc = coerce_scenario(scenario)
        await self.financial.warn_if_legacy_project_costs_exist()
        cons = await self.financial.calcular_consolidado_global(competencia=competencia, scenario=sc)
        return {
            "project_id": None,
            "competencia": competencia,
            "revenue_total": cons["revenue_total"],
            "total_revenue": cons["total_revenue"],
            "cost_total": cons["total_cost"],
            "total_cost": cons["total_cost"],
            "total_retention": cons["total_retention"],
            "operational_profit": cons["operational_profit"],
            "net_profit": cons["net_profit"],
            "margin_operational": cons["margin_operational"],
            "margin_net": cons["margin_net"],
            "ebitda": cons["ebitda"],
            "ebitda_margin": cons["ebitda_margin"],
            "profit": cons["profit"],
            "margin": cons["margin"],
            "operational_cost": cons["operational_cost"],
            "labor_cost": cons["labor_cost"],
            "vehicle_cost": cons["vehicle_cost"],
            "system_cost": cons["system_cost"],
            "fixed_operational_cost": cons["fixed_operational_cost"],
            "tax_amount": cons["tax_amount"],
            "overhead_amount": cons["overhead_amount"],
            "anticipation_amount": cons["anticipation_amount"],
            "labor_cost_pct": cons["labor_cost_pct"],
            "vehicle_cost_pct": cons["vehicle_cost_pct"],
            "system_cost_pct": cons["system_cost_pct"],
            "fixed_operational_cost_pct": cons["fixed_operational_cost_pct"],
            "operational_cost_pct": cons["operational_cost_pct"],
            "tax_amount_pct": cons["tax_amount_pct"],
            "overhead_amount_pct": cons["overhead_amount_pct"],
            "anticipation_amount_pct": cons["anticipation_amount_pct"],
        }

    async def serie_mensal(
        self, *, project_id: UUID | None, months: int = 6, scenario: str | Scenario = DEFAULT_SCENARIO
    ) -> list[dict]:
        sc = coerce_scenario(scenario)
        out: list[dict] = []
        for comp in _last_n_month_first_days(months):
            if project_id is not None:
                cons = await self.financial.calcular_consolidado_projeto(
                    project_id=project_id, competencia=comp, scenario=sc
                )
            else:
                cons = await self.financial.calcular_consolidado_global(competencia=comp, scenario=sc)
            out.append(_consolidado_to_monthly_row(comp, cons))
        return out

    async def kpis_por_mes(self, *, competencia: date, project_id: UUID | None = None) -> list[KPI]:
        stmt = select(KPI).where(KPI.competencia == competencia)
        if project_id:
            stmt = stmt.where(KPI.project_id == project_id)
        else:
            stmt = stmt.where(KPI.project_id.is_(None))
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def list_projects_financial_summaries(
        self, *, competencia: date, project_ids: list[UUID], scenario: str | Scenario = DEFAULT_SCENARIO
    ) -> list[dict]:
        """Consolidado por projeto na competência — mesmos números que `resumo_por_projeto` / `calcular_consolidado_projeto`."""
        sc = coerce_scenario(scenario)
        comp = normalize_competencia(competencia)
        await self.financial.warn_if_legacy_project_costs_exist()
        out: list[dict] = []
        for pid in project_ids:
            proj = await self.session.get(Project, pid)
            if not proj:
                continue
            s = await self.resumo_por_projeto(project_id=pid, competencia=comp, scenario=sc)
            rev = float(s["total_revenue"])
            margin_net = float(s["margin_net"]) if rev > 0 else 0.0
            out.append(
                {
                    "projeto": proj.name,
                    "project_id": pid,
                    "faturamento": rev,
                    "folha": float(s["labor_cost"]),
                    "veiculos": float(s["vehicle_cost"]),
                    "sistemas": float(s["system_cost"]),
                    "custos_fixos_operacionais": float(s["fixed_operational_cost"]),
                    "impostos": float(s["tax_amount"]),
                    "rateio": float(s["overhead_amount"]),
                    "antecipacao": float(s["anticipation_amount"]),
                    "retencao": float(s["total_retention"]),
                    "lucro_operacional": float(s["operational_profit"]),
                    "lucro_liquido": float(s["net_profit"]),
                    "margem": margin_net,
                }
            )
        out.sort(key=lambda r: r["faturamento"], reverse=True)
        return out
