from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.costs import ProjectCost
from app.models.financial import Revenue
from app.models.project_operational import ProjectLabor, ProjectOperationalFixed, ProjectSystemCost, ProjectVehicle
from app.services.employee_cost_service import calculate_clt_cost, calculate_pj_total_cost
from app.utils.date_utils import normalize_competencia

logger = logging.getLogger(__name__)

_legacy_project_costs_warning_done = False


def custo_percentual_receita(cost: float, receita: float) -> float:
    """Percentual do custo sobre a receita (0–100), 1 casa decimal; receita ≤ 0 → 0."""
    if receita <= 0:
        return 0.0
    return round((float(cost) / float(receita)) * 100.0, 1)


class FinancialService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def warn_if_legacy_project_costs_exist(self) -> None:
        """Avisa uma vez por processo se ainda houver linhas em project_costs (ignoradas nos cálculos)."""
        global _legacy_project_costs_warning_done
        if _legacy_project_costs_warning_done:
            return
        stmt = select(func.count()).select_from(ProjectCost)
        n = int((await self.session.execute(stmt)).scalar_one())
        if n > 0:
            logger.warning(
                "Existem %d registro(s) na tabela legada project_costs (/expenses); "
                "eles não entram mais em custos, dashboard ou margem.",
                n,
            )
        _legacy_project_costs_warning_done = True

    async def calcular_receita_total(self, *, project_id: UUID | None, competencia: date) -> float:
        comp = normalize_competencia(competencia)
        stmt = select(func.coalesce(func.sum(Revenue.amount), 0)).where(Revenue.competencia == comp)
        if project_id:
            stmt = stmt.where(Revenue.project_id == project_id)
        res = await self.session.execute(stmt)
        return float(res.scalar_one())

    async def calcular_total_retencao(self, *, project_id: UUID | None, competencia: date) -> float:
        """Soma 10% do valor bruto por lançamento com has_retention (alinhado a revenue_retention_value)."""
        comp = normalize_competencia(competencia)
        retention_line = case((Revenue.has_retention.is_(True), Revenue.amount * 0.10), else_=0)
        stmt = select(func.coalesce(func.sum(retention_line), 0)).where(Revenue.competencia == comp)
        if project_id is not None:
            stmt = stmt.where(Revenue.project_id == project_id)
        res = await self.session.execute(stmt)
        return round(float(res.scalar_one()), 2)

    async def calcular_lucro(self, *, project_id: UUID | None, competencia: date) -> float:
        if project_id is not None:
            cons = await self.calcular_consolidado_projeto(project_id=project_id, competencia=competencia)
        else:
            cons = await self.calcular_consolidado_global(competencia=competencia)
        return float(cons["profit"])

    async def calcular_margem(self, *, project_id: UUID | None, competencia: date) -> float:
        if project_id is not None:
            cons = await self.calcular_consolidado_projeto(project_id=project_id, competencia=competencia)
        else:
            cons = await self.calcular_consolidado_global(competencia=competencia)
        return float(cons["margin"])

    async def get_settings_row(self):
        from app.services.settings_service import SettingsService

        return await SettingsService(self.session).get_or_create()

    async def _sum_operational_column(
        self, model, column, *, project_id: UUID | None, competencia: date
    ) -> float:
        stmt = select(func.coalesce(func.sum(column), 0)).where(model.competencia == competencia)
        if project_id is not None:
            stmt = stmt.where(model.project_id == project_id)
        res = await self.session.execute(stmt)
        return float(res.scalar_one())

    async def _sum_labor_costs_derived(self, *, project_id: UUID | None, competencia: date) -> float:
        comp = normalize_competencia(competencia)
        stmt = (
            select(ProjectLabor)
            .options(selectinload(ProjectLabor.employee))
            .where(ProjectLabor.competencia == comp)
        )
        if project_id is not None:
            stmt = stmt.where(ProjectLabor.project_id == project_id)
        rows = (await self.session.execute(stmt)).scalars().all()
        settings = await self.get_settings_row()
        total = 0.0
        for row in rows:
            emp = row.employee
            if not emp:
                continue
            if (emp.employment_type or "").strip().upper() == "CLT":
                full = float(calculate_clt_cost(emp, settings, comp.year, comp.month))
            else:
                full = float(calculate_pj_total_cost(emp))
            factor = float(row.allocation_percentage) / 100.0
            total += full * factor
        return total

    async def calcular_operacional_estruturado(
        self, *, project_id: UUID | None, competencia: date
    ) -> dict:
        labor = await self._sum_labor_costs_derived(project_id=project_id, competencia=competencia)
        vehicle = await self._sum_operational_column(
            ProjectVehicle, ProjectVehicle.monthly_cost, project_id=project_id, competencia=competencia
        )
        system = await self._sum_operational_column(
            ProjectSystemCost, ProjectSystemCost.value, project_id=project_id, competencia=competencia
        )
        fixed = await self._sum_operational_column(
            ProjectOperationalFixed, ProjectOperationalFixed.value, project_id=project_id, competencia=competencia
        )
        operational = labor + vehicle + system + fixed
        return {
            "labor_cost": labor,
            "vehicle_cost": vehicle,
            "system_cost": system,
            "fixed_operational_cost": fixed,
            "operational_cost": operational,
        }

    async def calcular_consolidado_projeto(self, *, project_id: UUID, competencia: date) -> dict:
        settings = await self.get_settings_row()
        receita = await self.calcular_receita_total(project_id=project_id, competencia=competencia)
        total_retention = await self.calcular_total_retencao(project_id=project_id, competencia=competencia)
        parts = await self.calcular_operacional_estruturado(project_id=project_id, competencia=competencia)
        tax = receita * float(settings.tax_rate)
        overhead = receita * float(settings.overhead_rate)
        anticipation = receita * float(settings.anticipation_rate)
        total_cost = parts["operational_cost"] + tax + overhead + anticipation
        operational_profit = receita - total_cost
        net_profit = operational_profit - total_retention
        margin_operational = 0.0 if receita == 0 else float(operational_profit / receita)
        margin_net = 0.0 if receita == 0 else float(net_profit / receita)
        ebitda = receita - parts["operational_cost"]
        ebitda_margin = 0.0 if receita == 0 else float(ebitda / receita)
        p = custo_percentual_receita
        return {
            "revenue_total": receita,
            "total_revenue": receita,
            **parts,
            "tax_amount": tax,
            "overhead_amount": overhead,
            "anticipation_amount": anticipation,
            "total_cost": total_cost,
            "total_retention": total_retention,
            "operational_profit": operational_profit,
            "net_profit": net_profit,
            "margin_operational": margin_operational,
            "margin_net": margin_net,
            "ebitda": ebitda,
            "ebitda_margin": ebitda_margin,
            "profit": operational_profit,
            "margin": margin_operational,
            "labor_cost_pct": p(parts["labor_cost"], receita),
            "vehicle_cost_pct": p(parts["vehicle_cost"], receita),
            "system_cost_pct": p(parts["system_cost"], receita),
            "fixed_operational_cost_pct": p(parts["fixed_operational_cost"], receita),
            "operational_cost_pct": p(parts["operational_cost"], receita),
            "tax_amount_pct": p(tax, receita),
            "overhead_amount_pct": p(overhead, receita),
            "anticipation_amount_pct": p(anticipation, receita),
        }

    async def calcular_consolidado_global(self, *, competencia: date) -> dict:
        settings = await self.get_settings_row()
        receita = await self.calcular_receita_total(project_id=None, competencia=competencia)
        total_retention = await self.calcular_total_retencao(project_id=None, competencia=competencia)
        parts = await self.calcular_operacional_estruturado(project_id=None, competencia=competencia)
        tax = receita * float(settings.tax_rate)
        overhead = receita * float(settings.overhead_rate)
        anticipation = receita * float(settings.anticipation_rate)
        total_cost = parts["operational_cost"] + tax + overhead + anticipation
        operational_profit = receita - total_cost
        net_profit = operational_profit - total_retention
        margin_operational = 0.0 if receita == 0 else float(operational_profit / receita)
        margin_net = 0.0 if receita == 0 else float(net_profit / receita)
        ebitda = receita - parts["operational_cost"]
        ebitda_margin = 0.0 if receita == 0 else float(ebitda / receita)
        p = custo_percentual_receita
        return {
            "revenue_total": receita,
            "total_revenue": receita,
            **parts,
            "tax_amount": tax,
            "overhead_amount": overhead,
            "anticipation_amount": anticipation,
            "total_cost": total_cost,
            "total_retention": total_retention,
            "operational_profit": operational_profit,
            "net_profit": net_profit,
            "margin_operational": margin_operational,
            "margin_net": margin_net,
            "ebitda": ebitda,
            "ebitda_margin": ebitda_margin,
            "profit": operational_profit,
            "margin": margin_operational,
            "labor_cost_pct": p(parts["labor_cost"], receita),
            "vehicle_cost_pct": p(parts["vehicle_cost"], receita),
            "system_cost_pct": p(parts["system_cost"], receita),
            "fixed_operational_cost_pct": p(parts["fixed_operational_cost"], receita),
            "operational_cost_pct": p(parts["operational_cost"], receita),
            "tax_amount_pct": p(tax, receita),
            "overhead_amount_pct": p(overhead, receita),
            "anticipation_amount_pct": p(anticipation, receita),
        }
