from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import UUIDTimestampRead


class VehicleRead(UUIDTimestampRead):
    """Resposta da frota: JSON usa `type` e `active` (aliases)."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, serialize_by_alias=True)

    plate: str
    model: str | None = None
    description: str | None = None
    vehicle_type: str = Field(serialization_alias="type")
    monthly_cost: float
    driver_employee_id: UUID | None = None
    driver_name: str | None = None
    is_active: bool = Field(serialization_alias="active")


class VehicleCreate(BaseModel):
    plate: str = Field(min_length=4, max_length=20)
    model: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=255)
    vehicle_type: Literal["LIGHT", "PICKUP", "SEDAN"] = "LIGHT"
    monthly_cost: float = Field(ge=0, description="Custo fixo mensal (R$); padrão vem das configurações por tipo.")
    driver_employee_id: UUID | None = None
    is_active: bool = True


class VehicleUpdate(BaseModel):
    plate: str | None = Field(default=None, min_length=4, max_length=20)
    model: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=255)
    vehicle_type: Literal["LIGHT", "PICKUP", "SEDAN"] | None = None
    monthly_cost: float | None = Field(default=None, ge=0)
    driver_employee_id: UUID | None = None
    is_active: bool | None = None


class VehicleUsageRead(UUIDTimestampRead):
    vehicle_id: UUID
    project_id: UUID
    scenario: str = "REALIZADO"
    usage_date: date
    competencia: date
    cost_amount: float
    notes: str | None = None


class VehicleUsageCreate(BaseModel):
    vehicle_id: UUID
    project_id: UUID
    usage_date: date
    competencia: date
    cost_amount: float = Field(default=0, ge=0)
    notes: str | None = Field(default=None, max_length=255)
    scenario: str | None = None
