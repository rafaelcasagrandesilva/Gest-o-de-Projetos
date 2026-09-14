"""Resultado da Empresa (Indicadores): cascata projetos → custos indiretos → endividamento.

Campos monetários/percentuais são Optional: `company_result.sensitive` os omite (None).
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class CompanyResultMonthRead(BaseModel):
    competencia: date | None = None
    # Projetos (motor do Dashboard Operacional)
    revenue: float | None = None
    direct_cost: float | None = None
    labor_cost: float | None = None
    vehicle_cost: float | None = None
    system_cost: float | None = None
    fixed_operational_cost: float | None = None
    # Antecipação por instituição (R$; soma = anticipation_amount).
    anticipation_by_institution: dict[str, float] | None = None
    # Mês fechado: mão de obra pela folha PAGA / frota pela fatura rateada paga (senão estimativa).
    labor_real: bool = False
    vehicle_real: bool = False
    # REALIZADO: custos diretos lançados no CAP e ainda não pagos (fora do resultado).
    direct_open_cost: float | None = None
    contribution_margin: float | None = None
    # Regime tributário do mês ("LUCRO_PRESUMIDO" | "LUCRO_REAL"; None = reserva; "MISTO" no período).
    tax_regime: str | None = None
    tax_amount: float | None = None
    tax_rate: float | None = None
    tax_pis: float | None = None
    tax_cofins: float | None = None
    tax_iss: float | None = None
    tax_irpj: float | None = None
    tax_csll: float | None = None
    # IRPJ/CSLL sobre o LUCRO da empresa (só em mês de Lucro Real).
    profit_tax_amount: float | None = None
    anticipation_amount: float | None = None
    anticipation_rate: float | None = None
    anticipation_partial: bool = False
    operational_profit: float | None = None
    retention: float | None = None
    available_profit: float | None = None
    # Empresa
    indirect_cost: float | None = None
    indirect_labor_cost: float | None = None
    indirect_supplier_cost: float | None = None
    indirect_open_cost: float | None = None
    indirect_projected: bool = False
    debt_cost: float | None = None
    debt_open_cost: float | None = None
    debt_projected: bool = False
    # Mês fechado: custos indiretos/endividamento pelo VALOR PAGO; o não pago vai para *_open_cost.
    paid_basis: bool = False
    # Contas do mês seguinte (que o faturamento do mês paga) ainda em pagamento: valor final dos títulos.
    company_costs_partial: bool = False
    company_result: float | None = None
    available_margin: float | None = None
    coverage: float | None = None
    # Fração da receita que teria que sobrar (lucro disponível) para pagar indiretos + IR/CSLL + dívidas.
    required_margin: float | None = None
    # Faturamento para fechar 0 a 0 no mês/período e a diferença para a receita atual (+ = faltou).
    break_even_revenue: float | None = None
    revenue_gap: float | None = None


class CompanyResultIndirectCategoryRead(BaseModel):
    category: str
    amount: float | None = None


class CompanyResultIndirectItemRead(BaseModel):
    item_id: UUID | None = None
    name: str
    category: str
    is_labor: bool = False
    amount: float | None = None


class CompanyResultDebtItemRead(BaseModel):
    item_id: UUID | None = None
    name: str
    amount: float | None = None


class CompanyResultRead(BaseModel):
    scenario: str
    # Base dos custos: "PAGO" (REALIZADO, pago até agora) | "LANCADO" (PREVISTO, tudo o que foi lançado).
    basis: str | None = None
    period_start: date
    period_end: date
    month_count: int
    totals: CompanyResultMonthRead
    months: list[CompanyResultMonthRead] = Field(default_factory=list)
    indirect_by_category: list[CompanyResultIndirectCategoryRead] = Field(default_factory=list)
    indirect_items: list[CompanyResultIndirectItemRead] = Field(default_factory=list)
    debt_items: list[CompanyResultDebtItemRead] = Field(default_factory=list)
