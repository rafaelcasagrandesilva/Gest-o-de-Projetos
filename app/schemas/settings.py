from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

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
    tax_rate: float | None = Field(default=None, ge=0)
    overhead_rate: float | None = Field(default=None, ge=0)
    anticipation_rate: float | None = Field(default=None, ge=0)
    clt_charges_rate: float | None = Field(default=None, ge=0)
    vehicle_light_cost: float | None = Field(default=None, ge=0)
    vehicle_pickup_cost: float | None = Field(default=None, ge=0)
    vehicle_sedan_cost: float | None = Field(default=None, ge=0)
    vr_value: float | None = Field(default=None, ge=0)
    fuel_ethanol: float | None = Field(default=None, ge=0)
    fuel_gasoline: float | None = Field(default=None, ge=0)
    fuel_diesel: float | None = Field(default=None, ge=0)
    # km/L — 0 é aceito (combustível previsto por km fica 0 quando consumo é 0; ver operational_cost_calc).
    consumption_light: float | None = Field(default=None, ge=0)
    consumption_pickup: float | None = Field(default=None, ge=0)
    consumption_sedan: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def normalize_fraction_rates(self) -> "SystemSettingsUpdate":
        """
        Aceita fração 0–1 ou, para valores digitados como percentual inteiro, 2–100 (ex.: 9 → 0,09).
        Evita tratar 1,05 (fração) como 105%.
        """
        for name in ("tax_rate", "overhead_rate", "anticipation_rate", "clt_charges_rate"):
            v = getattr(self, name)
            if v is None:
                continue
            if v > 100:
                raise ValueError(
                    f"{name}: use entre 0 e 1 (ex.: 0,09) ou um inteiro de 2 a 100 (ex.: 9 para 9%)."
                )
            if v > 1 and v <= 100 and float(v).is_integer():
                setattr(self, name, round(v / 100.0, 8))
            elif v > 1:
                raise ValueError(
                    f"{name}: valor máximo em fração é 1 (100%). Ex.: 0,09 para 9%; ou digite 9 (inteiro) para 9%."
                )
        return self
