from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    ROLE_ADMIN,
    ROLE_CONSULTA,
    ROLE_GESTOR,
    _user_role_names,
    get_current_user,
    require_project_access,
    require_roles,
)
from app.core.scenario import Scenario, coerce_scenario
from app.database.session import get_db
from app.models.user import User
from app.schemas.dashboard import (
    DirectorSummary,
    FinancialDashboardSummary,
    KPIRead,
    MonthlyPoint,
    ProjectDashboardResponse,
    ProjectSummary,
)
from app.services.dashboard_service import DashboardService
from app.utils.date_utils import iter_competencias_inclusive, normalize_competencia, period_last_n_months


logger = logging.getLogger(__name__)

router = APIRouter()

_DASHBOARD_SUMMARY_ROLES = frozenset({ROLE_ADMIN, ROLE_GESTOR, ROLE_CONSULTA})


def _resolve_dashboard_period(
    competencia: date | None,
    start_date: date | None,
    end_date: date | None,
    months: int | None,
) -> tuple[date, date]:
    today = date.today()
    anchor = normalize_competencia(
        competencia if competencia is not None else date(today.year, today.month, 1)
    )
    if start_date is not None or end_date is not None:
        if start_date is None or end_date is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Informe start_date e end_date juntos.",
            )
        s = normalize_competencia(start_date)
        e = normalize_competencia(end_date)
        if s > e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_date não pode ser posterior a end_date.",
            )
        return s, e
    if months is not None:
        return period_last_n_months(anchor, months)
    return anchor, anchor


@router.get("/projects/{project_id}/summary", response_model=ProjectSummary)
async def project_summary(
    project_id: UUID,
    competencia: date,
    scenario_param: str | None = Query(
        default=None, alias="scenario", description="PREVISTO ou REALIZADO; omitir = REALIZADO"
    ),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_project_access),
) -> ProjectSummary:
    sc = coerce_scenario(scenario_param)
    try:
        data = await DashboardService(db).resumo_por_projeto(
            project_id=project_id, competencia=competencia, scenario=sc
        )
        return ProjectSummary.model_validate(data)
    except Exception:
        logger.exception("Erro em dashboard/projects/{id}/summary")
        raise


@router.get("/summary", response_model=FinancialDashboardSummary)
async def financial_summary(
    competencia: date | None = None,
    start_date: date | None = Query(default=None, description="Início do período (1º do mês)"),
    end_date: date | None = Query(default=None, description="Fim do período (1º do mês)"),
    project_id: UUID | None = Query(default=None),
    months: int | None = Query(
        default=None,
        ge=1,
        le=24,
        description="Últimos N meses terminando no mês-âncora (competência ou mês atual). Omitir = mês único.",
    ),
    scenario_param: str | None = Query(
        default=None, alias="scenario", description="PREVISTO ou REALIZADO; omitir = REALIZADO"
    ),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FinancialDashboardSummary:
    roles = _user_role_names(user)
    if not roles.intersection(_DASHBOARD_SUMMARY_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão.")
    can_global = ROLE_ADMIN in roles or ROLE_CONSULTA in roles
    if project_id is None and not can_global:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selecione um projeto para visualizar o dashboard.",
        )
    if project_id is not None:
        await require_project_access(project_id=project_id, user=user, db=db)

    sc = coerce_scenario(scenario_param)
    try:
        period_start, period_end = _resolve_dashboard_period(
            competencia, start_date, end_date, months
        )
        month_count = len(iter_competencias_inclusive(period_start, period_end))
        svc = DashboardService(db)
        s = await svc.resumo_period(
            project_id=project_id,
            start=period_start,
            end=period_end,
            scenario=sc,
        )
        series_prev = await svc.serie_mensal_interval(
            project_id=project_id,
            start=period_start,
            end=period_end,
            scenario=Scenario.PREVISTO,
        )
        series_real = await svc.serie_mensal_interval(
            project_id=project_id,
            start=period_start,
            end=period_end,
            scenario=Scenario.REALIZADO,
        )
        monthly_for_scenario = series_real if sc == Scenario.REALIZADO else series_prev
        lp, lr = await svc.lucro_liquido_previsto_e_realizado_period(
            project_id=project_id,
            start=period_start,
            end=period_end,
        )
        return FinancialDashboardSummary(
            scenario=sc.value,
            summary=DirectorSummary.model_validate(s),
            monthly_series=[MonthlyPoint.model_validate(x) for x in monthly_for_scenario],
            monthly_series_previsto=[MonthlyPoint.model_validate(x) for x in series_prev],
            monthly_series_realizado=[MonthlyPoint.model_validate(x) for x in series_real],
            period_start=period_start,
            period_end=period_end,
            month_count=month_count,
            lucro_liquido_previsto=lp,
            lucro_liquido_realizado=lr,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Erro em dashboard/summary")
        raise


@router.get("/project/{project_id}", response_model=ProjectDashboardResponse)
async def project_financial_dashboard(
    project_id: UUID,
    competencia: date | None = None,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    months: int | None = Query(
        default=None,
        ge=1,
        le=24,
        description="Últimos N meses; omitir = mês único (âncora em competência ou mês atual).",
    ),
    scenario_param: str | None = Query(default=None, alias="scenario", description="Omitir = REALIZADO"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_project_access),
) -> ProjectDashboardResponse:
    sc = coerce_scenario(scenario_param)
    try:
        period_start, period_end = _resolve_dashboard_period(
            competencia, start_date, end_date, months
        )
        month_count = len(iter_competencias_inclusive(period_start, period_end))
        svc = DashboardService(db)
        s = await svc.resumo_period(
            project_id=project_id,
            start=period_start,
            end=period_end,
            scenario=sc,
        )
        series_prev = await svc.serie_mensal_interval(
            project_id=project_id,
            start=period_start,
            end=period_end,
            scenario=Scenario.PREVISTO,
        )
        series_real = await svc.serie_mensal_interval(
            project_id=project_id,
            start=period_start,
            end=period_end,
            scenario=Scenario.REALIZADO,
        )
        monthly_for_scenario = series_real if sc == Scenario.REALIZADO else series_prev
        return ProjectDashboardResponse(
            summary=ProjectSummary.model_validate(s),
            monthly_series=[MonthlyPoint.model_validate(x) for x in monthly_for_scenario],
            monthly_series_previsto=[MonthlyPoint.model_validate(x) for x in series_prev],
            monthly_series_realizado=[MonthlyPoint.model_validate(x) for x in series_real],
            period_start=period_start,
            period_end=period_end,
            month_count=month_count,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Erro em dashboard/project/{id}")
        raise


@router.get("/director/summary", response_model=DirectorSummary, dependencies=[Depends(require_roles(ROLE_ADMIN))])
async def director_summary(
    competencia: date,
    scenario_param: str | None = Query(default=None, alias="scenario", description="Omitir = REALIZADO"),
    db: AsyncSession = Depends(get_db),
) -> DirectorSummary:
    sc = coerce_scenario(scenario_param)
    try:
        data = await DashboardService(db).resumo_geral_diretor(competencia=competencia, scenario=sc)
        return DirectorSummary.model_validate(data)
    except Exception:
        logger.exception("Erro em dashboard/director/summary")
        raise


@router.get("/kpis", response_model=list[KPIRead])
async def kpis(
    competencia: date,
    project_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[KPIRead]:
    roles = _user_role_names(user)
    if not roles.intersection(_DASHBOARD_SUMMARY_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão.")
    if project_id is None and ROLE_GESTOR in roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Informe project_id para visualizar KPIs.",
        )
    if project_id is not None:
        _ = await require_project_access(project_id=project_id, user=user, db=db)
    rows = await DashboardService(db).kpis_por_mes(competencia=competencia, project_id=project_id)
    return [KPIRead.model_validate(r) for r in rows]
