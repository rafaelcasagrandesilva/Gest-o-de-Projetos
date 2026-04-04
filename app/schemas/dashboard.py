from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampRead


class ProjectResultRead(UUIDTimestampRead):
    project_id: UUID
    competencia: date
    revenue_total: float
    total_revenue: float
    cost_total: float
    total_cost: float
    total_retention: float
    operational_profit: float
    net_profit: float
    margin_operational: float
    margin_net: float
    profit: float
    margin: float


class KPIRead(UUIDTimestampRead):
    project_id: UUID | None
    competencia: date
    name: str
    value: float


class MonthlyPoint(BaseModel):
    competencia: date
    revenue_total: float
    total_revenue: float
    cost_total: float
    total_cost: float
    total_retention: float = 0
    operational_profit: float = 0
    net_profit: float = 0
    margin_operational: float = 0
    margin_net: float = 0
    profit: float
    margin: float
    ebitda: float = 0
    ebitda_margin: float = 0
    operational_cost: float = 0
    tax_amount: float = 0
    overhead_amount: float = 0
    anticipation_amount: float = 0
    labor_cost_pct: float = 0
    vehicle_cost_pct: float = 0
    system_cost_pct: float = 0
    fixed_operational_cost_pct: float = 0
    operational_cost_pct: float = 0
    tax_amount_pct: float = 0
    overhead_amount_pct: float = 0
    anticipation_amount_pct: float = 0


class ProjectSummary(BaseModel):
    project_id: UUID
    competencia: date
    revenue_total: float
    total_revenue: float
    cost_total: float
    total_cost: float
    total_retention: float = 0
    operational_profit: float = 0
    net_profit: float = 0
    margin_operational: float = 0
    margin_net: float = 0
    profit: float
    margin: float
    ebitda: float = 0
    ebitda_margin: float = 0
    # Estrutura operacional + regras configuráveis
    operational_cost: float = 0
    labor_cost: float = 0
    vehicle_cost: float = 0
    system_cost: float = 0
    fixed_operational_cost: float = 0
    tax_amount: float = 0
    overhead_amount: float = 0
    anticipation_amount: float = 0
    labor_cost_pct: float = 0
    vehicle_cost_pct: float = 0
    system_cost_pct: float = 0
    fixed_operational_cost_pct: float = 0
    operational_cost_pct: float = 0
    tax_amount_pct: float = 0
    overhead_amount_pct: float = 0
    anticipation_amount_pct: float = 0


class DirectorSummary(BaseModel):
    project_id: UUID | None = None
    competencia: date
    revenue_total: float
    total_revenue: float
    cost_total: float
    total_cost: float
    total_retention: float = 0
    operational_profit: float = 0
    net_profit: float = 0
    margin_operational: float = 0
    margin_net: float = 0
    profit: float
    margin: float
    ebitda: float = 0
    ebitda_margin: float = 0
    operational_cost: float = 0
    labor_cost: float = 0
    vehicle_cost: float = 0
    system_cost: float = 0
    fixed_operational_cost: float = 0
    tax_amount: float = 0
    overhead_amount: float = 0
    anticipation_amount: float = 0
    labor_cost_pct: float = 0
    vehicle_cost_pct: float = 0
    system_cost_pct: float = 0
    fixed_operational_cost_pct: float = 0
    operational_cost_pct: float = 0
    tax_amount_pct: float = 0
    overhead_amount_pct: float = 0
    anticipation_amount_pct: float = 0


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
    lucro_liquido_previsto: float = 0.0
    lucro_liquido_realizado: float = 0.0


class ProjectDashboardResponse(BaseModel):
    summary: ProjectSummary
    monthly_series: list[MonthlyPoint]
    monthly_series_previsto: list[MonthlyPoint] = Field(default_factory=list)
    monthly_series_realizado: list[MonthlyPoint] = Field(default_factory=list)
    period_start: date | None = None
    period_end: date | None = None
    month_count: int | None = None
