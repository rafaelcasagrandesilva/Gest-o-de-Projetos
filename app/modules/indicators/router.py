from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.permission_codes import INDICATORS_DIRECTOR, INDICATORS_VIEW
from app.database.session import get_db
from app.schemas.indicators import (
    ConsolidatedRoi,
    KpiCatalog,
    ProjectRoi,
    RoiEvolution,
    RoiRanking,
)
from app.services.indicators_service import IndicatorsService
from app.utils.date_utils import normalize_competencia

logger = logging.getLogger(__name__)

router = APIRouter()

# Catálogo de KPIs do módulo. Apenas ROI Operacional disponível; demais previstos.
_KPI_CATALOG: list[dict] = [
    {"code": "roi_operacional", "name": "ROI Operacional", "status": "available"},
    {"code": "roi_colaborador", "name": "ROI por Colaborador", "status": "coming_soon"},
    {"code": "roi_cliente", "name": "ROI por Cliente", "status": "coming_soon"},
    {"code": "payback", "name": "Payback", "status": "coming_soon"},
    {"code": "margens", "name": "Margens", "status": "coming_soon"},
    {"code": "produtividade", "name": "Produtividade", "status": "coming_soon"},
    {"code": "indicadores_operacionais", "name": "Indicadores Operacionais", "status": "coming_soon"},
]


def _resolve_competencia(competencia: date | None) -> date:
    if competencia is not None:
        return normalize_competencia(competencia)
    today = date.today()
    return normalize_competencia(date(today.year, today.month, 1))


def _resolve_range(data_inicial: date | None, data_final: date | None) -> tuple[date, date]:
    """Normaliza um intervalo [início, fim]. Um dos lados ausente = mês único do outro."""
    today = date.today()
    anchor = normalize_competencia(date(today.year, today.month, 1))
    start = normalize_competencia(data_inicial) if data_inicial is not None else None
    end = normalize_competencia(data_final) if data_final is not None else None
    if start is None and end is None:
        start = end = anchor
    elif start is None:
        start = end
    elif end is None:
        end = start
    if start > end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="data_inicial não pode ser posterior a data_final.",
        )
    return start, end


def _parse_project_ids(raw: str | None) -> list[UUID] | None:
    if not raw or not raw.strip():
        return None
    out: list[UUID] = []
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        try:
            out.append(UUID(token))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"project_id inválido: {token}",
            )
    return out or None


@router.get(
    "/roi/operacional",
    response_model=RoiRanking,
    dependencies=[Depends(require_permission(INDICATORS_VIEW))],
)
async def roi_operacional_ranking(
    competencia: date | None = Query(default=None, description="1º do mês; omitir = mês atual"),
    data_inicial: date | None = Query(default=None, description="Início do intervalo (acumulado)"),
    data_final: date | None = Query(default=None, description="Fim do intervalo (acumulado)"),
    scenario_param: str | None = Query(
        default=None, alias="scenario", description="PREVISTO ou REALIZADO; omitir = REALIZADO"
    ),
    db: AsyncSession = Depends(get_db),
) -> RoiRanking:
    svc = IndicatorsService(db)
    if data_inicial is not None or data_final is not None:
        start, end = _resolve_range(data_inicial, data_final)
        data = await svc.roi_operacional_ranking_range(start=start, end=end, scenario=scenario_param)
    else:
        comp = _resolve_competencia(competencia)
        data = await svc.roi_operacional_ranking(competencia=comp, scenario=scenario_param)
    return RoiRanking.model_validate(data)


@router.get(
    "/roi/projetos/{project_id}",
    response_model=ProjectRoi,
    dependencies=[Depends(require_permission(INDICATORS_VIEW))],
)
async def roi_operacional_projeto(
    project_id: UUID,
    competencia: date | None = Query(default=None, description="1º do mês; omitir = mês atual"),
    scenario_param: str | None = Query(
        default=None, alias="scenario", description="PREVISTO ou REALIZADO; omitir = REALIZADO"
    ),
    db: AsyncSession = Depends(get_db),
) -> ProjectRoi:
    comp = _resolve_competencia(competencia)
    data = await IndicatorsService(db).roi_operacional_projeto(
        project_id=project_id, competencia=comp, scenario=scenario_param
    )
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado.")
    return ProjectRoi.model_validate(data)


@router.get(
    "/roi/consolidado",
    response_model=ConsolidatedRoi,
    dependencies=[Depends(require_permission(INDICATORS_DIRECTOR))],
)
async def roi_consolidado(
    competencia: date | None = Query(default=None, description="1º do mês; omitir = mês atual"),
    data_inicial: date | None = Query(default=None, description="Início do intervalo (acumulado)"),
    data_final: date | None = Query(default=None, description="Fim do intervalo (acumulado)"),
    scenario_param: str | None = Query(
        default=None, alias="scenario", description="PREVISTO ou REALIZADO; omitir = REALIZADO"
    ),
    project_ids: str | None = Query(
        default=None, description="UUIDs separados por vírgula; omitir/vazio = todos os ativos"
    ),
    db: AsyncSession = Depends(get_db),
) -> ConsolidatedRoi:
    svc = IndicatorsService(db)
    ids = _parse_project_ids(project_ids)
    if data_inicial is not None or data_final is not None:
        start, end = _resolve_range(data_inicial, data_final)
        data = await svc.consolidado_range(start=start, end=end, scenario=scenario_param, project_ids=ids)
    else:
        comp = _resolve_competencia(competencia)
        data = await svc.consolidado(competencia=comp, scenario=scenario_param, project_ids=ids)
    return ConsolidatedRoi.model_validate(data)


@router.get(
    "/roi/evolucao",
    response_model=RoiEvolution,
    dependencies=[Depends(require_permission(INDICATORS_VIEW))],
)
async def roi_evolucao(
    data_inicial: date = Query(..., description="Início do intervalo (1º do mês)"),
    data_final: date = Query(..., description="Fim do intervalo (1º do mês)"),
    scenario_param: str | None = Query(
        default=None, alias="scenario", description="PREVISTO ou REALIZADO; omitir = REALIZADO"
    ),
    project_ids: str | None = Query(
        default=None, description="UUIDs separados por vírgula; omitir/vazio = todos os ativos"
    ),
    db: AsyncSession = Depends(get_db),
) -> RoiEvolution:
    start = normalize_competencia(data_inicial)
    end = normalize_competencia(data_final)
    if start > end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="data_inicial não pode ser posterior a data_final.",
        )
    ids = _parse_project_ids(project_ids)
    data = await IndicatorsService(db).evolucao(start=start, end=end, scenario=scenario_param, project_ids=ids)
    return RoiEvolution.model_validate(data)


@router.get(
    "/catalog",
    response_model=KpiCatalog,
    dependencies=[Depends(require_permission(INDICATORS_VIEW))],
)
async def kpi_catalog() -> KpiCatalog:
    return KpiCatalog.model_validate({"items": _KPI_CATALOG})
