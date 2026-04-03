from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard import KPI
from app.models.project import Project
from app.services.financial_service import FinancialService
from app.utils.date_utils import normalize_competencia


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


class DashboardService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.financial = FinancialService(session)

    async def resumo_por_projeto(self, *, project_id: UUID, competencia: date) -> dict:
        await self.financial.warn_if_legacy_project_costs_exist()
        cons = await self.financial.calcular_consolidado_projeto(project_id=project_id, competencia=competencia)
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

    async def resumo_geral_diretor(self, *, competencia: date) -> dict:
        await self.financial.warn_if_legacy_project_costs_exist()
        cons = await self.financial.calcular_consolidado_global(competencia=competencia)
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

    async def serie_mensal(self, *, project_id: UUID | None, months: int = 6) -> list[dict]:
        out: list[dict] = []
        for comp in _last_n_month_first_days(months):
            if project_id is not None:
                cons = await self.financial.calcular_consolidado_projeto(project_id=project_id, competencia=comp)
            else:
                cons = await self.financial.calcular_consolidado_global(competencia=comp)
            out.append(
                {
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
            )
        return out

    async def kpis_por_mes(self, *, competencia: date, project_id: UUID | None = None) -> list[KPI]:
        stmt = select(KPI).where(KPI.competencia == competencia)
        if project_id:
            stmt = stmt.where(KPI.project_id == project_id)
        else:
            stmt = stmt.where(KPI.project_id.is_(None))
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def list_projects_financial_summaries(self, *, competencia: date, project_ids: list[UUID]) -> list[dict]:
        """Consolidado por projeto na competência — mesmos números que `resumo_por_projeto` / `calcular_consolidado_projeto`."""
        comp = normalize_competencia(competencia)
        await self.financial.warn_if_legacy_project_costs_exist()
        out: list[dict] = []
        for pid in project_ids:
            proj = await self.session.get(Project, pid)
            if not proj:
                continue
            s = await self.resumo_por_projeto(project_id=pid, competencia=comp)
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
