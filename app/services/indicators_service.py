from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scenario import Scenario, coerce_scenario
from app.repositories.projects import ProjectRepository
from app.services.financial_service import FinancialService
from app.utils.date_utils import iter_competencias_inclusive, normalize_competencia


# --- Regras puras (testáveis sem banco) -------------------------------------

# Tolerância monetária: valores até meio centavo são tratados como zero
# (alinhado ao arredondamento de 2 casas em app/utils/money.py).
MOVEMENT_TOLERANCE = 0.005


def is_economically_relevant(
    revenue: float, cost: float, *, tol: float = MOVEMENT_TOLERANCE
) -> bool:
    """Regra única de elegibilidade de um projeto para os Indicadores.

    Elegível quando houve movimentação econômica no período:
        receita_total_periodo > 0  OU  custo_total_periodo > 0
    (com tolerância monetária). Independe de `is_active`, `closed_at` ou status
    operacional — a única exclusão obrigatória (feita antes, na origem dos
    projetos) é `deleted_at IS NOT NULL`.
    """
    return revenue > tol or cost > tol


def compute_roi(operational_profit: float, total_cost: float) -> float | None:
    """ROI Operacional = lucro operacional / custo total.

    Retorna None quando o custo é <= 0 (investimento indefinido), nunca 0,
    para distinguir "sem investimento" de "ROI zero".
    """
    if total_cost <= 0:
        return None
    return operational_profit / total_cost


def _roi_sort_key(item: dict) -> tuple[int, float]:
    """Ordena ROI desc; itens com roi None vão para o fim (preservando estabilidade)."""
    roi = item.get("roi")
    if roi is None:
        return (1, 0.0)
    return (0, -float(roi))


def sort_roi_desc(items: list[dict]) -> list[dict]:
    """Ordena uma lista de dicts de ROI do maior para o menor; None ao fim."""
    return sorted(items, key=_roi_sort_key)


def aggregate_consolidado(rows: list[dict]) -> dict:
    """Consolida métricas de vários projetos.

    ROI consolidado = Σ operational_profit / Σ total_cost (NUNCA média dos ROIs).
    """
    revenue = sum(float(r.get("revenue", 0.0)) for r in rows)
    cost = sum(float(r.get("cost", 0.0)) for r in rows)
    operational_profit = sum(float(r.get("operational_profit", 0.0)) for r in rows)
    roi = compute_roi(operational_profit, cost)
    return {
        "revenue": revenue,
        "cost": cost,
        "operational_profit": operational_profit,
        "roi": roi,
        "roi_pct": None if roi is None else roi * 100.0,
        "project_count": len(rows),
    }


# --- Serviço (compõe FinancialService como única fonte de verdade) ----------


class IndicatorsService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._financial = FinancialService(session)
        self._projects = ProjectRepository(session)

    async def _project_roi_dict(
        self, *, project_id: UUID, project_name: str, competencia: date, scenario: Scenario
    ) -> dict:
        consolidado = await self._financial.calcular_consolidado_projeto(
            project_id=project_id, competencia=competencia, scenario=scenario
        )
        revenue = float(consolidado["total_revenue"])
        cost = float(consolidado["total_cost"])
        operational_profit = float(consolidado["operational_profit"])
        roi = compute_roi(operational_profit, cost)
        return {
            "project_id": project_id,
            "project_name": project_name,
            "competencia": competencia,
            "scenario": scenario.value,
            "revenue": revenue,
            "cost": cost,
            "operational_profit": operational_profit,
            "roi": roi,
            "roi_pct": None if roi is None else roi * 100.0,
        }

    async def _project_roi_range_dict(
        self, *, project_id: UUID, project_name: str, start: date, end: date, scenario: Scenario
    ) -> dict:
        """ROI acumulado de um projeto no intervalo [start, end] (Σ meses).

        Quando start == end equivale a um único mês. Toda receita/custo/lucro
        vem do FinancialService mês a mês; aqui apenas somamos.
        """
        revenue = 0.0
        cost = 0.0
        operational_profit = 0.0
        for comp in iter_competencias_inclusive(start, end):
            consolidado = await self._financial.calcular_consolidado_projeto(
                project_id=project_id, competencia=comp, scenario=scenario
            )
            revenue += float(consolidado["total_revenue"])
            cost += float(consolidado["total_cost"])
            operational_profit += float(consolidado["operational_profit"])
        roi = compute_roi(operational_profit, cost)
        return {
            "project_id": project_id,
            "project_name": project_name,
            "competencia": start,
            "scenario": scenario.value,
            "revenue": revenue,
            "cost": cost,
            "operational_profit": operational_profit,
            "roi": roi,
            "roi_pct": None if roi is None else roi * 100.0,
        }

    async def eligible_projects_for_indicators(
        self, *, start: date, end: date, scenario: Scenario
    ) -> list[dict]:
        """Conjunto ÚNICO de projetos elegíveis para os Indicadores no período.

        Candidatos = todos os projetos não-deletados (ativos + encerrados);
        mantém-se apenas os economicamente relevantes no intervalo [start, end]
        (`is_economically_relevant`). Cada item é o dict de ROI acumulado do
        projeto, pronto para ranking/consolidado/contagem — toda receita/custo
        vem do FinancialService (regras financeiras intocadas).

        Esta é a função reutilizável que centraliza a regra `receita>0 OR custo>0`,
        evitando espalhá-la pelo módulo.
        """
        projects = await self._projects.list_not_deleted()
        rows = [
            await self._project_roi_range_dict(
                project_id=p.id, project_name=p.name, start=start, end=end, scenario=scenario
            )
            for p in projects
        ]
        return [r for r in rows if is_economically_relevant(r["revenue"], r["cost"])]

    async def roi_operacional_projeto(
        self, *, project_id: UUID, competencia: date, scenario: str | Scenario = Scenario.REALIZADO
    ) -> dict | None:
        sc = coerce_scenario(scenario)
        project = await self._projects.get(project_id)
        if project is None or getattr(project, "deleted_at", None) is not None:
            return None
        return await self._project_roi_dict(
            project_id=project.id,
            project_name=project.name,
            competencia=competencia,
            scenario=sc,
        )

    async def roi_operacional_ranking(
        self, *, competencia: date, scenario: str | Scenario = Scenario.REALIZADO
    ) -> dict:
        """Ranking de ROI dos projetos elegíveis no mês (receita ou custo > 0)."""
        sc = coerce_scenario(scenario)
        items = await self.eligible_projects_for_indicators(
            start=competencia, end=competencia, scenario=sc
        )
        return {
            "competencia": competencia,
            "scenario": sc.value,
            # only_active: mantido por compatibilidade da API/frontend. NÃO significa
            # mais "projeto ativo" — agora indica "projeto elegível para indicadores"
            # (movimentação econômica no período; encerrados com movimento entram).
            "only_active": True,
            "items": sort_roi_desc(items),
        }

    async def roi_operacional_ranking_range(
        self, *, start: date, end: date, scenario: str | Scenario = Scenario.REALIZADO
    ) -> dict:
        """Ranking de ROI acumulado dos projetos elegíveis no intervalo [start, end]."""
        sc = coerce_scenario(scenario)
        items = await self.eligible_projects_for_indicators(start=start, end=end, scenario=sc)
        return {
            "competencia": start,
            "scenario": sc.value,
            # Ver nota em roi_operacional_ranking: "elegível", não "ativo".
            "only_active": True,
            "items": sort_roi_desc(items),
        }

    async def consolidado_range(
        self,
        *,
        start: date,
        end: date,
        scenario: str | Scenario = Scenario.REALIZADO,
        project_ids: list[UUID] | None = None,
    ) -> dict:
        """Consolidado acumulado no intervalo [start, end]. ROI = Σlucro/Σcusto."""
        sc = coerce_scenario(scenario)
        targets = await self._resolve_project_ids(project_ids, start=start, end=end, scenario=sc)
        rows = [
            await self._project_roi_range_dict(
                project_id=pid, project_name=name, start=start, end=end, scenario=sc
            )
            for pid, name in targets
        ]
        agg = aggregate_consolidado(rows)
        return {
            "competencia": start,
            "scenario": sc.value,
            "project_ids": [pid for pid, _ in targets],
            "revenue": agg["revenue"],
            "cost": agg["cost"],
            "operational_profit": agg["operational_profit"],
            "roi": agg["roi"],
            "roi_pct": agg["roi_pct"],
            "project_count": agg["project_count"],
        }

    async def _resolve_project_ids(
        self, project_ids: list[UUID] | None, *, start: date, end: date, scenario: Scenario
    ) -> list[tuple[UUID, str]]:
        """Resolve a lista de (id, nome) a consolidar.

        Sem ids = todos os projetos ELEGÍVEIS no período (receita ou custo > 0),
        não mais "todos os ativos". Com ids explícitos = respeita a seleção do
        usuário (que já vem da lista elegível do ranking), excluindo apenas
        projetos inexistentes ou deletados.
        """
        if not project_ids:
            rows = await self.eligible_projects_for_indicators(
                start=start, end=end, scenario=scenario
            )
            return [(r["project_id"], r["project_name"]) for r in rows]
        out: list[tuple[UUID, str]] = []
        for pid in project_ids:
            project = await self._projects.get(pid)
            if project is not None and getattr(project, "deleted_at", None) is None:
                out.append((project.id, project.name))
        return out

    async def consolidado(
        self,
        *,
        competencia: date,
        scenario: str | Scenario = Scenario.REALIZADO,
        project_ids: list[UUID] | None = None,
    ) -> dict:
        sc = coerce_scenario(scenario)
        targets = await self._resolve_project_ids(
            project_ids, start=competencia, end=competencia, scenario=sc
        )
        rows = [
            await self._project_roi_dict(
                project_id=pid, project_name=name, competencia=competencia, scenario=sc
            )
            for pid, name in targets
        ]
        agg = aggregate_consolidado(rows)
        return {
            "competencia": competencia,
            "scenario": sc.value,
            "project_ids": [pid for pid, _ in targets],
            "revenue": agg["revenue"],
            "cost": agg["cost"],
            "operational_profit": agg["operational_profit"],
            "roi": agg["roi"],
            "roi_pct": agg["roi_pct"],
            "project_count": agg["project_count"],
        }

    async def evolucao(
        self,
        *,
        start: date,
        end: date,
        scenario: str | Scenario = Scenario.REALIZADO,
        project_ids: list[UUID] | None = None,
    ) -> list[dict]:
        """Série mensal consolidada entre start e end (inclusive)."""
        sc = coerce_scenario(scenario)
        norm_start = normalize_competencia(start)
        norm_end = normalize_competencia(end)
        targets = await self._resolve_project_ids(
            project_ids, start=norm_start, end=norm_end, scenario=sc
        )
        target_ids = [pid for pid, _ in targets]
        out: list[dict] = []
        for comp in iter_competencias_inclusive(norm_start, norm_end):
            rows = [
                await self._project_roi_dict(
                    project_id=pid, project_name=name, competencia=comp, scenario=sc
                )
                for pid, name in targets
            ]
            agg = aggregate_consolidado(rows)
            out.append(
                {
                    "competencia": comp,
                    "revenue": agg["revenue"],
                    "cost": agg["cost"],
                    "operational_profit": agg["operational_profit"],
                    "roi": agg["roi"],
                    "roi_pct": agg["roi_pct"],
                }
            )
        return {"scenario": sc.value, "project_ids": target_ids, "points": out}
