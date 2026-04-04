from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampRead


class ProjectFixedCostRead(UUIDTimestampRead):
    project_id: UUID
    competencia: date
    scenario: str = "REALIZADO"
    name: str
    amount_real: float
    amount_calculated: float


class ProjectFixedCostCreate(BaseModel):
    project_id: UUID
    competencia: date
    name: str = Field(min_length=2, max_length=255)
    amount_real: float = Field(ge=0)
    amount_calculated: float = Field(default=0, ge=0)
    scenario: str | None = None


class CorporateCostRead(UUIDTimestampRead):
    competencia: date
    name: str
    amount_real: float
    amount_calculated: float


class CorporateCostCreate(BaseModel):
    competencia: date
    name: str = Field(min_length=2, max_length=255)
    amount_real: float = Field(ge=0)
    amount_calculated: float = Field(default=0, ge=0)


class CostAllocationRead(UUIDTimestampRead):
    corporate_cost_id: UUID
    project_id: UUID
    competencia: date
    allocated_amount_real: float
    allocated_amount_calculated: float


class CostAllocationCreate(BaseModel):
    corporate_cost_id: UUID
    project_id: UUID
    competencia: date
    allocated_amount_real: float = Field(ge=0)
    allocated_amount_calculated: float = Field(default=0, ge=0)

