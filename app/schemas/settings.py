from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampRead


class SystemSettingsRead(UUIDTimestampRead):
    tax_rate: float
    overhead_rate: float
    anticipation_rate: float
    clt_charges_rate: float
    vehicle_light_cost: float = Field(
        description="Padrão leve (R$/mês) — sugerido no cadastro de veículo (leve_default_cost).",
    )
    vehicle_pickup_cost: float = Field(
        description="Padrão pickup (R$/mês) — sugerido no cadastro (pickup_default_cost).",
    )
    vehicle_sedan_cost: float = Field(
        description="Padrão sedan (R$/mês) — sugerido no cadastro (sedan_default_cost).",
    )
    vr_value: float
    fuel_ethanol: float
    fuel_gasoline: float
    fuel_diesel: float
    consumption_light: float
    consumption_pickup: float
    consumption_sedan: float


class SystemSettingsUpdate(BaseModel):
    tax_rate: float | None = Field(default=None, ge=0, le=1)
    overhead_rate: float | None = Field(default=None, ge=0, le=1)
    anticipation_rate: float | None = Field(default=None, ge=0, le=1)
    clt_charges_rate: float | None = Field(default=None, ge=0, le=1)
    vehicle_light_cost: float | None = Field(default=None, ge=0)
    vehicle_pickup_cost: float | None = Field(default=None, ge=0)
    vehicle_sedan_cost: float | None = Field(default=None, ge=0)
    vr_value: float | None = Field(default=None, ge=0)
    fuel_ethanol: float | None = Field(default=None, ge=0)
    fuel_gasoline: float | None = Field(default=None, ge=0)
    fuel_diesel: float | None = Field(default=None, ge=0)
    consumption_light: float | None = Field(default=None, gt=0)
    consumption_pickup: float | None = Field(default=None, gt=0)
    consumption_sedan: float | None = Field(default=None, gt=0)
