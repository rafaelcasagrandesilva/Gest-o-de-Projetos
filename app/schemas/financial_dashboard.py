from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class FinancialDashboardSummaryRead(BaseModel):
    month: date = Field(..., description="Mês âncora (YYYY-MM-01).")
    period_start: date = Field(..., description="Início do período (YYYY-MM-01).")
    period_end: date = Field(..., description="Fim do período (YYYY-MM-01).")
    faturamento: float = Field(..., description="Total recebido do cliente no período (regime de caixa).")
    pago: float = Field(..., description="Total pago no período (regime de caixa).")
    caixa: float = Field(..., description="Caixa = recebido - pago no período.")


class FinancialDashboardTimeseriesPoint(BaseModel):
    month: date = Field(..., description="Competência (YYYY-MM-01).")
    faturamento: float
    pago: float
    caixa: float


FinancialDashboardBreakdownType = Literal["faturamento", "custos", "caixa"]


class FinancialDashboardGroupedItem(BaseModel):
    label: str
    value: float


class FinancialDashboardBreakdownRead(BaseModel):
    type: FinancialDashboardBreakdownType
    month: date
    total: float
    groups: list[FinancialDashboardGroupedItem] = Field(default_factory=list)
    received_total: float | None = None
    received_groups: list[FinancialDashboardGroupedItem] | None = None
    paid_total: float | None = None
    paid_groups: list[FinancialDashboardGroupedItem] | None = None


class FinancialDashboardRead(BaseModel):
    summary: FinancialDashboardSummaryRead
    timeseries: list[FinancialDashboardTimeseriesPoint]

