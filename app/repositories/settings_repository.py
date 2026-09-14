from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import SystemSettings


class SystemSettingsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_singleton(self) -> SystemSettings | None:
        # Deveria haver UMA linha, mas bancos já nasceram com duplicata (duas criações
        # simultâneas no primeiro acesso). Sem ORDER BY o Postgres devolvia qualquer uma —
        # inclusive a zerada, que nunca foi editada. Vale a última editada, sempre a mesma.
        res = await self.session.execute(
            select(SystemSettings)
            .order_by(SystemSettings.updated_at.desc(), SystemSettings.created_at.desc())
            .limit(1)
        )
        return res.scalar_one_or_none()

    async def add(self, row: SystemSettings) -> SystemSettings:
        self.session.add(row)
        await self.session.flush()
        return row
