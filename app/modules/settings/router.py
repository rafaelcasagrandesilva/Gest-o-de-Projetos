from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ROLE_ADMIN, require_roles
from app.database.session import get_db
from app.schemas.settings import SystemSettingsRead, SystemSettingsUpdate
from app.services.settings_service import SettingsService


router = APIRouter(dependencies=[Depends(require_roles(ROLE_ADMIN))])


@router.get("", response_model=SystemSettingsRead)
async def get_settings(db: AsyncSession = Depends(get_db)) -> SystemSettingsRead:
    row = await SettingsService(db).get_or_create()
    return SystemSettingsRead.model_validate(row)


@router.put("", response_model=SystemSettingsRead)
async def put_settings(
    payload: SystemSettingsUpdate,
    db: AsyncSession = Depends(get_db),
) -> SystemSettingsRead:
    row = await SettingsService(db).update(payload.model_dump(exclude_unset=True))
    return SystemSettingsRead.model_validate(row)
