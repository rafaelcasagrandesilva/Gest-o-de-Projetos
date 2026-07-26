from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.permission_codes import SETTINGS_READ, SETTINGS_UPDATE
from app.database.session import get_db
from app.schemas.payment_component_type import (
    PaymentComponentTypeCreate,
    PaymentComponentTypeRead,
    PaymentComponentTypeUpdate,
)
from app.schemas.settings import SystemSettingsRead, SystemSettingsUpdate
from app.services.payment_component_type_service import PaymentComponentTypeService
from app.services.settings_service import SettingsService


router = APIRouter()

_READ = [Depends(require_permission(SETTINGS_READ))]
_EDIT = [Depends(require_permission(SETTINGS_UPDATE))]


@router.get("", response_model=SystemSettingsRead, dependencies=[Depends(require_permission(SETTINGS_READ))])
async def get_settings(db: AsyncSession = Depends(get_db)) -> SystemSettingsRead:
    row = await SettingsService(db).get_or_create()
    return SystemSettingsRead.model_validate(row)


@router.put("", response_model=SystemSettingsRead, dependencies=[Depends(require_permission(SETTINGS_UPDATE))])
async def put_settings(
    payload: SystemSettingsUpdate,
    db: AsyncSession = Depends(get_db),
) -> SystemSettingsRead:
    row = await SettingsService(db).update(payload.model_dump(exclude_unset=True))
    return SystemSettingsRead.model_validate(row)


# ------------------------------------------------------------------ #
# Cadastro: Tipos de Componentes Variáveis de Pagamento (data-driven)
# ------------------------------------------------------------------ #
def _type_read(row, usage: int) -> PaymentComponentTypeRead:
    data = PaymentComponentTypeRead.model_validate(row)
    data.usage_count = usage
    return data


@router.get("/payment-component-types", response_model=list[PaymentComponentTypeRead], dependencies=_READ)
async def list_payment_component_types(
    only_active: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> list[PaymentComponentTypeRead]:
    svc = PaymentComponentTypeService(db)
    rows = await svc.list(only_active=only_active)
    usage = await svc.usage_counts([r.id for r in rows])
    return [_type_read(r, usage.get(r.id, 0)) for r in rows]


@router.post("/payment-component-types", response_model=PaymentComponentTypeRead, dependencies=_EDIT)
async def create_payment_component_type(
    payload: PaymentComponentTypeCreate,
    db: AsyncSession = Depends(get_db),
) -> PaymentComponentTypeRead:
    svc = PaymentComponentTypeService(db)
    try:
        row = await svc.create(payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return _type_read(row, 0)


@router.patch("/payment-component-types/{type_id}", response_model=PaymentComponentTypeRead, dependencies=_EDIT)
async def update_payment_component_type(
    type_id: UUID,
    payload: PaymentComponentTypeUpdate,
    db: AsyncSession = Depends(get_db),
) -> PaymentComponentTypeRead:
    svc = PaymentComponentTypeService(db)
    try:
        row = await svc.update(type_id, payload.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if row is None:
        raise HTTPException(status_code=404, detail="Tipo não encontrado.")
    usage = await svc.usage_counts([row.id])
    await db.commit()
    return _type_read(row, usage.get(row.id, 0))


@router.delete("/payment-component-types/{type_id}", status_code=204, dependencies=_EDIT)
async def delete_payment_component_type(
    type_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = PaymentComponentTypeService(db)
    try:
        ok = await svc.delete(type_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="Tipo não encontrado.")
    await db.commit()
