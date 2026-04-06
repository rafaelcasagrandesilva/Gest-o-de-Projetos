from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.permission_codes import ALERTS_VIEW, SYSTEM_ADMIN
from app.database.session import get_db
from app.schemas.alerts import AlertRead, AlertResolveRequest
from app.services.alerts_service import AlertsService


_read = [Depends(require_permission(ALERTS_VIEW))]

router = APIRouter()


@router.get("/", response_model=list[AlertRead], dependencies=_read)
async def list_alerts(
    db: AsyncSession = Depends(get_db),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AlertRead]:
    rows = await AlertsService(db).list_alerts(offset=offset, limit=limit)
    return [AlertRead.model_validate(r) for r in rows]


@router.post("/checks/invoices-due", response_model=list[AlertRead], dependencies=[Depends(require_permission(SYSTEM_ADMIN))])
async def check_invoices_due(
    today: date,
    days_ahead: int = Query(default=7, ge=1, le=60),
    db: AsyncSession = Depends(get_db),
) -> list[AlertRead]:
    rows = await AlertsService(db).check_contas_vencendo(today=today, days_ahead=days_ahead)
    return [AlertRead.model_validate(r) for r in rows]


@router.post("/checks/negative-margin", response_model=list[AlertRead], dependencies=[Depends(require_permission(SYSTEM_ADMIN))])
async def check_negative_margin(competencia: date, db: AsyncSession = Depends(get_db)) -> list[AlertRead]:
    rows = await AlertsService(db).check_margem_negativa(competencia=competencia)
    return [AlertRead.model_validate(r) for r in rows]


@router.patch("/{alert_id}", response_model=AlertRead, dependencies=[Depends(require_permission(SYSTEM_ADMIN))])
async def resolve_alert(alert_id, payload: AlertResolveRequest, db: AsyncSession = Depends(get_db)) -> AlertRead:
    try:
        row = await AlertsService(db).resolve_alert(alert_id=alert_id, is_resolved=payload.is_resolved)
    except ValueError:
        raise HTTPException(status_code=404, detail="Alerta não encontrado.")
    return AlertRead.model_validate(row)
