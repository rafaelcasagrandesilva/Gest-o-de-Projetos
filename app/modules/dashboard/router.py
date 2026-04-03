from __future__ import annotations

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


router = APIRouter()

_DASHBOARD_SUMMARY_ROLES = frozenset({ROLE_ADMIN, ROLE_GESTOR, ROLE_CONSULTA})


@router.get("/projects/{project_id}/summary", response_model=ProjectSummary)
async def project_summary(
    project_id: UUID,
    competencia: date,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_project_access),
) -> ProjectSummary:
    data = await DashboardService(db).resumo_por_projeto(project_id=project_id, competencia=competencia)
    return ProjectSummary.model_validate(data)


@router.get("/summary", response_model=FinancialDashboardSummary)
async def financial_summary(
    competencia: date | None = None,
    project_id: UUID | None = Query(default=None),
    months: int = Query(default=6, ge=1, le=24),
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

    today = date.today()
    comp = competencia or date(today.year, today.month, 1)
    svc = DashboardService(db)
    if project_id is None:
        s = await svc.resumo_geral_diretor(competencia=comp)
        series = await svc.serie_mensal(project_id=None, months=months)
    else:
        s = await svc.resumo_por_projeto(project_id=project_id, competencia=comp)
        series = await svc.serie_mensal(project_id=project_id, months=months)
    return FinancialDashboardSummary(
        summary=DirectorSummary.model_validate(s),
        monthly_series=[MonthlyPoint.model_validate(x) for x in series],
    )


@router.get("/project/{project_id}", response_model=ProjectDashboardResponse)
async def project_financial_dashboard(
    project_id: UUID,
    competencia: date | None = None,
    months: int = Query(default=6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_project_access),
) -> ProjectDashboardResponse:
    today = date.today()
    comp = competencia or date(today.year, today.month, 1)
    svc = DashboardService(db)
    s = await svc.resumo_por_projeto(project_id=project_id, competencia=comp)
    series = await svc.serie_mensal(project_id=project_id, months=months)
    return ProjectDashboardResponse(
        summary=ProjectSummary.model_validate(s),
        monthly_series=[MonthlyPoint.model_validate(x) for x in series],
    )


@router.get("/director/summary", response_model=DirectorSummary, dependencies=[Depends(require_roles(ROLE_ADMIN))])
async def director_summary(competencia: date, db: AsyncSession = Depends(get_db)) -> DirectorSummary:
    data = await DashboardService(db).resumo_geral_diretor(competencia=competencia)
    return DirectorSummary.model_validate(data)


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
