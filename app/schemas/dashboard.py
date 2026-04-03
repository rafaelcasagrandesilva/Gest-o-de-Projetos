from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel

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
    summary: DirectorSummary
    monthly_series: list[MonthlyPoint]


class ProjectDashboardResponse(BaseModel):
    summary: ProjectSummary
    monthly_series: list[MonthlyPoint]
