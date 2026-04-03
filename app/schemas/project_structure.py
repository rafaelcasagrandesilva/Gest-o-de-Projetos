from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import UUIDTimestampRead
from app.utils.date_utils import normalize_competencia


# --- Mão de obra (vínculo colaborador × competência) ---


class ProjectLaborRead(UUIDTimestampRead):
    project_id: UUID
    competencia: date
    employee_id: UUID
    allocation_percentage: float
    monthly_cost: float


class ProjectLaborCreate(BaseModel):
    competencia: date
    employee_id: UUID
    allocation_percentage: float = Field(default=100.0, ge=1, le=100)

    @field_validator("competencia", mode="after")
    @classmethod
    def competencia_primeiro_dia(cls, v: date) -> date:
        return normalize_competencia(v)


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


# --- Veículos ---


class ProjectVehicleRead(UUIDTimestampRead):
    project_id: UUID
    competencia: date
    vehicle_id: UUID
    plate: str
    model: str | None
    vehicle_type: str
    fuel_type: str
    km_per_month: float
    monthly_cost: float
    driver_employee_id: UUID | None = None
    driver_name: str | None = None


class ProjectVehicleCreate(BaseModel):
    competencia: date
    vehicle_id: UUID
    fuel_type: Literal["ETHANOL", "GASOLINE", "DIESEL"]
    km_per_month: float = Field(ge=0)

    @field_validator("competencia", mode="after")
    @classmethod
    def competencia_veiculo_primeiro_dia(cls, v: date) -> date:
        return normalize_competencia(v)


class ProjectVehicleUpdate(BaseModel):
    vehicle_id: UUID | None = None
    fuel_type: Literal["ETHANOL", "GASOLINE", "DIESEL"] | None = None
    km_per_month: float | None = Field(default=None, ge=0)


# --- Sistemas ---


class ProjectSystemCostRead(UUIDTimestampRead):
    project_id: UUID
    competencia: date
    name: str
    value: float


class ProjectSystemCostCreate(BaseModel):
    competencia: date
    name: str = Field(min_length=1, max_length=255)
    value: float = Field(ge=0)


class ProjectSystemCostUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    value: float | None = Field(default=None, ge=0)


# --- Custos fixos operacionais ---


class ProjectOperationalFixedRead(UUIDTimestampRead):
    project_id: UUID
    competencia: date
    name: str
    value: float


class ProjectOperationalFixedCreate(BaseModel):
    competencia: date
    name: str = Field(min_length=1, max_length=255)
    value: float = Field(ge=0)


class ProjectOperationalFixedUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    value: float | None = Field(default=None, ge=0)
