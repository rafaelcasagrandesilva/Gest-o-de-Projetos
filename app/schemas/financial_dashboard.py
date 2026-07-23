from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


# Dados Sensíveis: os campos monetários são Optional para que `redact_for` possa OMITI-LOS (None)
# quando o usuário não tem `financial_dashboard.sensitive`. Datas/labels permanecem (estruturais).
class FinancialDashboardSummaryRead(BaseModel):
    month: date = Field(..., description="Mês âncora (YYYY-MM-01).")
    period_start: date = Field(..., description="Início do período (YYYY-MM-01).")
    period_end: date = Field(..., description="Fim do período (YYYY-MM-01).")
    faturamento: float | None = Field(default=None, description="Total recebido do cliente no período (regime de caixa).")
    pago: float | None = Field(default=None, description="Total pago no período (regime de caixa).")
    caixa: float | None = Field(default=None, description="Caixa = recebido - pago no período.")


class FinancialDashboardTimeseriesPoint(BaseModel):
    month: date = Field(..., description="Competência (YYYY-MM-01).")
    faturamento: float | None = None
    pago: float | None = None
    caixa: float | None = None


FinancialDashboardBreakdownType = Literal["faturamento", "custos", "caixa"]


class FinancialDashboardGroupedItem(BaseModel):
    label: str
    value: float | None = None


class FinancialDashboardBreakdownRead(BaseModel):
    type: FinancialDashboardBreakdownType
    month: date
    total: float | None = None
    groups: list[FinancialDashboardGroupedItem] = Field(default_factory=list)
    received_total: float | None = None
    received_groups: list[FinancialDashboardGroupedItem] | None = None
    paid_total: float | None = None
    paid_groups: list[FinancialDashboardGroupedItem] | None = None


class FinancialDashboardRead(BaseModel):
    summary: FinancialDashboardSummaryRead
    timeseries: list[FinancialDashboardTimeseriesPoint]

