from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.permission_codes import SETTINGS_EDIT, SETTINGS_VIEW
from app.database.session import get_db
from app.schemas.settings import SystemSettingsRead, SystemSettingsUpdate
from app.services.settings_service import SettingsService


router = APIRouter()


@router.get("", response_model=SystemSettingsRead, dependencies=[Depends(require_permission(SETTINGS_VIEW))])
async def get_settings(db: AsyncSession = Depends(get_db)) -> SystemSettingsRead:
    row = await SettingsService(db).get_or_create()
    return SystemSettingsRead.model_validate(row)


@router.put("", response_model=SystemSettingsRead, dependencies=[Depends(require_permission(SETTINGS_EDIT))])
async def put_settings(
    payload: SystemSettingsUpdate,
    db: AsyncSession = Depends(get_db),
) -> SystemSettingsRead:
    row = await SettingsService(db).update(payload.model_dump(exclude_unset=True))
    return SystemSettingsRead.model_validate(row)
