from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import SystemSettings
from app.repositories.settings_repository import SystemSettingsRepository


def _default_settings() -> SystemSettings:
    return SystemSettings(
        tax_rate=0,
        overhead_rate=0,
        anticipation_rate=0,
        clt_charges_rate=0,
        vehicle_light_cost=0,
        vehicle_pickup_cost=0,
        vehicle_sedan_cost=0,
        vr_value=0,
        fuel_ethanol=0,
        fuel_gasoline=0,
        fuel_diesel=0,
        consumption_light=1,
        consumption_pickup=1,
        consumption_sedan=1,
    )


class SettingsService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = SystemSettingsRepository(session)

    async def get_or_create(self) -> SystemSettings:
        row = await self.repo.get_singleton()
        if row is None:
            row = _default_settings()
            await self.repo.add(row)
            await self.session.commit()
            await self.session.refresh(row)
        return row

    async def update(self, data: dict) -> SystemSettings:
        row = await self.get_or_create()
        patch = {k: v for k, v in data.items() if v is not None}
        for k, v in patch.items():
            setattr(row, k, v)
        await self.session.commit()
        await self.session.refresh(row)
        return row
