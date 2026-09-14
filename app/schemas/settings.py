from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import UUIDTimestampRead

AnticipationMode = Literal["AUTOMATICO", "FIXO"]
TaxRegime = Literal["LUCRO_PRESUMIDO", "LUCRO_REAL"]

# Campos percentuais aceitos como fração 0–1 ou inteiro 2–100 (ver normalize_fraction_rates).
# O limite mensal do adicional de IRPJ é dinheiro e fica FORA desta lista.
FRACTION_RATE_FIELDS: tuple[str, ...] = (
    "tax_rate",
    "overhead_rate",
    "anticipation_rate",
    "clt_charges_rate",
    "iss_rate",
    "pis_presumido_rate",
    "cofins_presumido_rate",
    "irpj_presumption_rate",
    "csll_presumption_rate",
    "irpj_rate",
    "irpj_additional_rate",
    "csll_rate",
    "pis_real_rate",
    "cofins_real_rate",
    "pis_cofins_credit_rate",
)


class SystemSettingsRead(UUIDTimestampRead):
    # Reserva: só vale nos meses sem regime tributário cadastrado.
    tax_rate: float
    overhead_rate: float
    anticipation_rate: float
    anticipation_mode: AnticipationMode = "AUTOMATICO"
    clt_charges_rate: float
    # Regime tributário
    iss_rate: float
    pis_presumido_rate: float
    cofins_presumido_rate: float
    irpj_presumption_rate: float
    csll_presumption_rate: float
    irpj_rate: float
    irpj_additional_rate: float
    irpj_additional_monthly_threshold: float
    csll_rate: float
    pis_real_rate: float
    cofins_real_rate: float
    pis_cofins_credit_rate: float
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
    anticipation_mode: AnticipationMode | None = None
    clt_charges_rate: float | None = Field(default=None, ge=0)
    iss_rate: float | None = Field(default=None, ge=0)
    pis_presumido_rate: float | None = Field(default=None, ge=0)
    cofins_presumido_rate: float | None = Field(default=None, ge=0)
    irpj_presumption_rate: float | None = Field(default=None, ge=0)
    csll_presumption_rate: float | None = Field(default=None, ge=0)
    irpj_rate: float | None = Field(default=None, ge=0)
    irpj_additional_rate: float | None = Field(default=None, ge=0)
    # R$ por mês — não é percentual.
    irpj_additional_monthly_threshold: float | None = Field(default=None, ge=0)
    csll_rate: float | None = Field(default=None, ge=0)
    pis_real_rate: float | None = Field(default=None, ge=0)
    cofins_real_rate: float | None = Field(default=None, ge=0)
    pis_cofins_credit_rate: float | None = Field(default=None, ge=0)
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
        for name in FRACTION_RATE_FIELDS:
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


class TaxRegimePeriodRead(UUIDTimestampRead):
    regime: TaxRegime
    start_date: date
    note: str | None = None


class TaxRegimePeriodCreate(BaseModel):
    regime: TaxRegime
    # Data em que o regime passa a valer; normalizada para o 1º dia do mês (competência).
    start_date: date
    note: str | None = Field(default=None, max_length=255)
