from __future__ import annotations

from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.scenario import DEFAULT_SCENARIO, Scenario, parse_scenario
from app.schemas.common import UUIDTimestampRead
from app.utils.date_utils import normalize_competencia


# --- Mão de obra (vínculo colaborador × competência) ---


class ProjectLaborRead(UUIDTimestampRead):
    project_id: UUID
    competencia: date
    scenario: str = "REALIZADO"
    employee_id: UUID
    allocation_percentage: float
    monthly_cost: float
    cost_base_source: str = "CADASTRO"
    cost_salary_base: float | None = None
    cost_additional_costs: float | None = None
    cost_extra_hours_50: float | None = None
    cost_extra_hours_70: float | None = None
    cost_extra_hours_100: float | None = None
    cost_pj_hours_per_month: float | None = None
    cost_pj_additional_cost: float | None = None
    cost_total_override: float | None = None


class ProjectLaborCreate(BaseModel):
    competencia: date
    employee_id: UUID
    allocation_percentage: float = Field(default=100.0, ge=1, le=100)
    scenario: str | None = Field(default=None, description="PREVISTO ou REALIZADO; padrão REALIZADO")

    @field_validator("competencia", mode="after")
    @classmethod
    def competencia_primeiro_dia(cls, v: date) -> date:
        return normalize_competencia(v)


class ProjectLaborCopyFromPreviousBody(BaseModel):
    """Copia vínculos do mês anterior para a competência informada (só colaboradores ainda não vinculados)."""

    competencia: date
    scenario: str | None = Field(default=None, description="PREVISTO ou REALIZADO; padrão REALIZADO")

    @field_validator("competencia", mode="after")
    @classmethod
    def competencia_primeiro_dia(cls, v: date) -> date:
        return normalize_competencia(v)


class ProjectLaborCopyFromPreviousResult(BaseModel):
    copied: int
    skipped_already_linked: int
    skipped_allocation_cap: int


def _coerce_optional_cost_number(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        if s == "":
            return None
        return float(s.replace(",", "."))
    return float(v)


class ProjectLaborCostUpdate(BaseModel):
    """Atualização de custos mensais no vínculo (não altera o cadastro global do colaborador)."""

    cost_salary_base: float | None = None
    cost_additional_costs: float | None = None
    cost_extra_hours_50: float | None = None
    cost_extra_hours_70: float | None = None
    cost_extra_hours_100: float | None = None
    cost_pj_hours_per_month: float | None = None
    cost_pj_additional_cost: float | None = None
    cost_total_override: float | None = None

    @field_validator(
        "cost_salary_base",
        "cost_additional_costs",
        "cost_extra_hours_50",
        "cost_extra_hours_70",
        "cost_extra_hours_100",
        "cost_pj_hours_per_month",
        "cost_pj_additional_cost",
        "cost_total_override",
        mode="before",
    )
    @classmethod
    def _coerce_nums(cls, v: Any) -> float | None:
        return _coerce_optional_cost_number(v)


class LaborCostBreakdown(BaseModel):
    salary_base: float
    periculosidade: float
    adicional_dirigida: float
    vr: float
    horas_extras: float
    encargos: float = 0
    additional_costs: float = 0
    ajuda_custo: float = 0


class ProjectLaborDetailItem(BaseModel):
    labor_id: UUID
    employee_id: UUID
    name: str
    tipo: str
    allocation_percentage: float
    full_cost: float
    allocated_cost: float
    total_cost: float
    breakdown: LaborCostBreakdown
    uses_cost_total_override: bool = False
    cost_base_source: str = "CADASTRO"
    cost_salary_base: float | None = None
    cost_additional_costs: float | None = None
    cost_extra_hours_50: float | None = None
    cost_extra_hours_70: float | None = None
    cost_extra_hours_100: float | None = None
    cost_pj_hours_per_month: float | None = None
    cost_pj_additional_cost: float | None = None
    cost_total_override: float | None = None


# --- Veículos ---


class ProjectVehicleRead(UUIDTimestampRead):
    project_id: UUID
    competencia: date
    scenario: str = "REALIZADO"
    vehicle_id: UUID
    plate: str
    model: str | None
    vehicle_type: str
    fuel_type: str | None = None
    km_per_month: float | None = None
    fuel_cost_realized: float | None = None
    monthly_cost: float
    # Combustível para comparativo previsto × realizado (previsto = estimado por km; realizado = informado).
    display_fuel_cost: float | None = None
    fuel_cost_per_km_realized: float | None = None
    driver_employee_id: UUID | None = None
    driver_name: str | None = None


class ProjectVehicleCreate(BaseModel):
    competencia: date
    vehicle_id: UUID
    scenario: str | None = Field(default=None, description="PREVISTO ou REALIZADO; padrão REALIZADO")
    fuel_type: Literal["ETHANOL", "GASOLINE", "DIESEL"] | None = None
    km_per_month: float | None = Field(default=None, ge=0)
    fuel_cost_realized: float | None = Field(default=None, ge=0)

    @field_validator("competencia", mode="after")
    @classmethod
    def competencia_veiculo_primeiro_dia(cls, v: date) -> date:
        return normalize_competencia(v)

    @model_validator(mode="after")
    def validate_by_scenario(self) -> ProjectVehicleCreate:
        sc = parse_scenario(self.scenario, default=DEFAULT_SCENARIO)
        if sc == Scenario.PREVISTO.value:
            if self.fuel_type is None:
                raise ValueError("tipo de combustível é obrigatório no cenário PREVISTO")
            if self.km_per_month is None:
                raise ValueError("km por mês é obrigatório no cenário PREVISTO")
        else:
            if self.fuel_cost_realized is None:
                raise ValueError("valor real de combustível (R$) é obrigatório no cenário REALIZADO")
        return self


class ProjectVehicleUpdate(BaseModel):
    vehicle_id: UUID | None = None
    fuel_type: Literal["ETHANOL", "GASOLINE", "DIESEL"] | None = None
    km_per_month: float | None = Field(default=None, ge=0)
    fuel_cost_realized: float | None = Field(default=None, ge=0)


# --- Sistemas ---


class ProjectSystemCostRead(UUIDTimestampRead):
    project_id: UUID
    competencia: date
    scenario: str = "REALIZADO"
    name: str
    value: float


class ProjectSystemCostCreate(BaseModel):
    competencia: date
    name: str = Field(min_length=1, max_length=255)
    value: float = Field(ge=0)
    scenario: str | None = None


class ProjectSystemCostUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    value: float | None = Field(default=None, ge=0)


# --- Custos fixos operacionais ---


class ProjectOperationalFixedRead(UUIDTimestampRead):
    project_id: UUID
    competencia: date
    scenario: str = "REALIZADO"
    name: str
    value: float


class ProjectOperationalFixedCreate(BaseModel):
    competencia: date
    name: str = Field(min_length=1, max_length=255)
    value: float = Field(ge=0)
    scenario: str | None = None


class ProjectOperationalFixedUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    value: float | None = Field(default=None, ge=0)
