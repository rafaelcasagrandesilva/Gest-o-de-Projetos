from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import SystemSettings


class SystemSettingsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_singleton(self) -> SystemSettings | None:
        res = await self.session.execute(select(SystemSettings).limit(1))
        return res.scalar_one_or_none()

    async def add(self, row: SystemSettings) -> SystemSettings:
        self.session.add(row)
        await self.session.flush()
        return row
