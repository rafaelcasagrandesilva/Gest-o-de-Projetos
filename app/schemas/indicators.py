from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel


class ProjectRoi(BaseModel):
    """ROI Operacional de um projeto em uma competência.

    ROI = operational_profit / total_cost (do FinancialService).
    `roi` é None quando total_cost <= 0 (investimento indefinido).
    """

    project_id: UUID
    project_name: str
    competencia: date
    scenario: str
    revenue: float | None = None
    cost: float | None = None
    operational_profit: float | None = None
    roi: float | None
    roi_pct: float | None


class RoiRanking(BaseModel):
    """Ranking de ROI Operacional dos projetos ELEGÍVEIS (ordenado desc; None ao fim).

    Elegibilidade = movimentação econômica no período (receita ou custo > 0),
    independente de status; exclui apenas projetos deletados.
    """

    competencia: date
    scenario: str
    # DEPRECADO SEMANTICAMENTE: mantido por compatibilidade de API/frontend.
    # NÃO significa mais "apenas projetos ativos" — agora indica "apenas projetos
    # elegíveis para indicadores" (com movimentação econômica no período; projetos
    # encerrados com receita/custo entram, ativos sem movimentação saem).
    only_active: bool
    items: list[ProjectRoi]


class ConsolidatedRoi(BaseModel):
    """ROI consolidado: Σ operational_profit / Σ total_cost (NUNCA média de ROIs)."""

    competencia: date
    scenario: str
    project_ids: list[UUID]
    project_count: int
    revenue: float | None = None
    cost: float | None = None
    operational_profit: float | None = None
    roi: float | None
    roi_pct: float | None


class RoiEvolutionPoint(BaseModel):
    competencia: date
    revenue: float | None = None
    cost: float | None = None
    operational_profit: float | None = None
    roi: float | None
    roi_pct: float | None


class RoiEvolution(BaseModel):
    scenario: str
    project_ids: list[UUID]
    points: list[RoiEvolutionPoint]


class KpiCatalogEntry(BaseModel):
    code: str
    name: str
    status: str  # "available" | "coming_soon"


class KpiCatalog(BaseModel):
    items: list[KpiCatalogEntry]


# --- Dashboard Executivo: Evolução Financeira -------------------------------


class FinancialEvolutionPoint(BaseModel):
    """Ponto mensal do Dashboard Executivo (sem Combustível, conforme escopo)."""

    competencia: date
    faturamento: float | None = None
    custo_mo: float | None = None
    custo_veiculos: float | None = None
    lucro_operacional: float | None = None
    lucro_liquido: float | None = None


class FinancialKpi(BaseModel):
    """Card de KPI: total acumulado no período + crescimento mês inicial→final."""

    total: float | None = None
    growth_pct: float | None


class FinancialKpis(BaseModel):
    faturamento: FinancialKpi
    custo_mo: FinancialKpi
    lucro_operacional: FinancialKpi
    lucro_liquido: FinancialKpi


class MonthlyHighlight(BaseModel):
    competencia: date
    value: float | None = None


class ProjectHighlight(BaseModel):
    project_id: UUID
    project_name: str
    value: float | None = None


class FinancialInsights(BaseModel):
    """Painel 'Insights' — destaques calculados automaticamente."""

    maior_faturamento: MonthlyHighlight | None
    menor_faturamento: MonthlyHighlight | None
    maior_lucro_operacional: MonthlyHighlight | None
    maior_lucro_liquido: MonthlyHighlight | None
    projeto_maior_faturamento: ProjectHighlight | None
    projeto_maior_lucro: ProjectHighlight | None
    tendencia: str  # "alta" | "baixa" | "estavel"
    crescimento_acumulado_pct: float | None


class FinancialEvolution(BaseModel):
    """Payload completo do Dashboard Executivo de Evolução Financeira."""

    scenario: str
    start: date
    end: date
    project_ids: list[UUID]
    cost_centers: list[str]
    project_count: int
    points: list[FinancialEvolutionPoint]
    kpis: FinancialKpis
    insights: FinancialInsights


class FilterProject(BaseModel):
    project_id: UUID
    project_name: str
    cost_center: str | None


class IndicatorFilters(BaseModel):
    """Opções de filtro disponíveis (apenas dimensões com cadastro estruturado)."""

    projects: list[FilterProject]
    cost_centers: list[str]
