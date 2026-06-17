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
    revenue: float
    cost: float
    operational_profit: float
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
    revenue: float
    cost: float
    operational_profit: float
    roi: float | None
    roi_pct: float | None


class RoiEvolutionPoint(BaseModel):
    competencia: date
    revenue: float
    cost: float
    operational_profit: float
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
