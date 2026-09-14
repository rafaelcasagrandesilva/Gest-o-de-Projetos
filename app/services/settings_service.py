from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import SystemSettings
from app.repositories.settings_repository import SystemSettingsRepository


def _default_settings() -> SystemSettings:
    return SystemSettings(
        tax_rate=0,
        overhead_rate=0,
        anticipation_rate=0,
        anticipation_mode="AUTOMATICO",
        clt_charges_rate=0,
        iss_rate=0.05,
        pis_presumido_rate=0.0065,
        cofins_presumido_rate=0.03,
        irpj_presumption_rate=0.32,
        csll_presumption_rate=0.32,
        irpj_rate=0.15,
        irpj_additional_rate=0.10,
        irpj_additional_monthly_threshold=20000,
        csll_rate=0.09,
        pis_real_rate=0.0165,
        cofins_real_rate=0.076,
        pis_cofins_credit_rate=0,
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
