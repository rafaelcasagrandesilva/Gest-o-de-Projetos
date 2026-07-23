from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampRead


class ProjectResultRead(UUIDTimestampRead):
    project_id: UUID
    competencia: date
    revenue_total: float | None = None
    total_revenue: float | None = None
    cost_total: float | None = None
    total_cost: float | None = None
    total_retention: float | None = None
    operational_profit: float | None = None
    net_profit: float | None = None
    margin_operational: float | None = None
    margin_net: float | None = None
    profit: float | None = None
    margin: float | None = None


class KPIRead(UUIDTimestampRead):
    project_id: UUID | None
    competencia: date
    name: str
    value: float | None = None


class MonthlyPoint(BaseModel):
    competencia: date
    revenue_total: float | None = None
    total_revenue: float | None = None
    cost_total: float | None = None
    total_cost: float | None = None
    total_retention: float | None = 0
    operational_profit: float | None = 0
    net_profit: float | None = 0
    margin_operational: float | None = 0
    margin_net: float | None = 0
    profit: float | None = None
    margin: float | None = None
    ebitda: float | None = 0
    ebitda_margin: float | None = 0
    operational_cost: float | None = 0
    labor_cost: float | None = 0
    vehicle_cost: float | None = 0
    system_cost: float | None = 0
    fixed_operational_cost: float | None = 0
    tax_amount: float | None = 0
    overhead_amount: float | None = 0
    anticipation_amount: float | None = 0
    labor_cost_pct: float | None = 0
    vehicle_cost_pct: float | None = 0
    system_cost_pct: float | None = 0
    fixed_operational_cost_pct: float | None = 0
    operational_cost_pct: float | None = 0
    tax_amount_pct: float | None = 0
    overhead_amount_pct: float | None = 0
    anticipation_amount_pct: float | None = 0


class ProjectSummary(BaseModel):
    project_id: UUID
    competencia: date
    revenue_total: float | None = None
    total_revenue: float | None = None
    cost_total: float | None = None
    total_cost: float | None = None
    total_retention: float | None = 0
    operational_profit: float | None = 0
    net_profit: float | None = 0
    margin_operational: float | None = 0
    margin_net: float | None = 0
    profit: float | None = None
    margin: float | None = None
    ebitda: float | None = 0
    ebitda_margin: float | None = 0
    # Estrutura operacional + regras configuráveis
    operational_cost: float | None = 0
    labor_cost: float | None = 0
    vehicle_cost: float | None = 0
    system_cost: float | None = 0
    fixed_operational_cost: float | None = 0
    tax_amount: float | None = 0
    overhead_amount: float | None = 0
    anticipation_amount: float | None = 0
    labor_cost_pct: float | None = 0
    vehicle_cost_pct: float | None = 0
    system_cost_pct: float | None = 0
    fixed_operational_cost_pct: float | None = 0
    operational_cost_pct: float | None = 0
    tax_amount_pct: float | None = 0
    overhead_amount_pct: float | None = 0
    anticipation_amount_pct: float | None = 0


class DirectorSummary(BaseModel):
    project_id: UUID | None = None
    competencia: date
    revenue_total: float | None = None
    total_revenue: float | None = None
    cost_total: float | None = None
    total_cost: float | None = None
    total_retention: float | None = 0
    operational_profit: float | None = 0
    net_profit: float | None = 0
    margin_operational: float | None = 0
    margin_net: float | None = 0
    profit: float | None = None
    margin: float | None = None
    ebitda: float | None = 0
    ebitda_margin: float | None = 0
    operational_cost: float | None = 0
    labor_cost: float | None = 0
    vehicle_cost: float | None = 0
    system_cost: float | None = 0
    fixed_operational_cost: float | None = 0
    tax_amount: float | None = 0
    overhead_amount: float | None = 0
    anticipation_amount: float | None = 0
    labor_cost_pct: float | None = 0
    vehicle_cost_pct: float | None = 0
    system_cost_pct: float | None = 0
    fixed_operational_cost_pct: float | None = 0
    operational_cost_pct: float | None = 0
    tax_amount_pct: float | None = 0
    overhead_amount_pct: float | None = 0
    anticipation_amount_pct: float | None = 0


class FinancialDashboardSummary(BaseModel):
    scenario: str = "REALIZADO"
    summary: DirectorSummary
    monthly_series: list[MonthlyPoint]
    """Série alinhada ao cenário solicitado (compatibilidade)."""
    monthly_series_previsto: list[MonthlyPoint] = Field(default_factory=list)
    monthly_series_realizado: list[MonthlyPoint] = Field(default_factory=list)
    period_start: date | None = None
    period_end: date | None = None
    month_count: int | None = None
    # net_profit consolidado (mesma regra do card "Lucro líquido"), competência do summary
    lucro_liquido_previsto: float | None = 0.0
    lucro_liquido_realizado: float | None = 0.0


class ProjectDashboardResponse(BaseModel):
    summary: ProjectSummary
    monthly_series: list[MonthlyPoint]
    monthly_series_previsto: list[MonthlyPoint] = Field(default_factory=list)
    monthly_series_realizado: list[MonthlyPoint] = Field(default_factory=list)
    period_start: date | None = None
    period_end: date | None = None
    month_count: int | None = None
