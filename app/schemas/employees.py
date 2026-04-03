from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import UUIDTimestampRead


class EmployeeRead(UUIDTimestampRead):
    full_name: str
    email: EmailStr | None = None
    role_title: str | None = None
    employment_type: str
    salary_base: float | None = None
    additional_costs: float | None = None
    total_cost: float
    is_active: bool
    has_periculosidade: bool = False
    has_adicional_dirigida: bool = False
    extra_hours_50: float = 0
    extra_hours_70: float = 0
    extra_hours_100: float = 0
    pj_hours_per_month: float | None = None
    pj_additional_cost: float = 0


class EmployeeCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr | None = None
    role_title: str | None = None
    employment_type: Literal["CLT", "PJ"] = "CLT"
    salary_base: float | None = Field(default=None, ge=0)
    additional_costs: float | None = Field(default=None, ge=0)
    is_active: bool = True
    has_periculosidade: bool = False
    has_adicional_dirigida: bool = False
    extra_hours_50: float = Field(default=0, ge=0)
    extra_hours_70: float = Field(default=0, ge=0)
    extra_hours_100: float = Field(default=0, ge=0)
    pj_hours_per_month: float | None = Field(default=None, ge=0)
    pj_additional_cost: float = Field(default=0, ge=0)
    cost_reference_competencia: date | None = Field(
        default=None,
        description="Primeiro dia do mês usado ao persistir custo CLT (VR e dias úteis). Padrão: mês corrente.",
    )


class EmployeeUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    email: EmailStr | None = None
    role_title: str | None = None
    employment_type: Literal["CLT", "PJ"] | None = None
    salary_base: float | None = Field(default=None, ge=0)
    additional_costs: float | None = Field(default=None, ge=0)
    is_active: bool | None = None
    has_periculosidade: bool | None = None
    has_adicional_dirigida: bool | None = None
    extra_hours_50: float | None = Field(default=None, ge=0)
    extra_hours_70: float | None = Field(default=None, ge=0)
    extra_hours_100: float | None = Field(default=None, ge=0)
    pj_hours_per_month: float | None = Field(default=None, ge=0)
    pj_additional_cost: float | None = Field(default=None, ge=0)
    cost_reference_competencia: date | None = Field(
        default=None,
        description="Mês ao salvar custo CLT no banco (primeiro dia). Padrão: mês corrente.",
    )


class CLTCostPreviewRequest(BaseModel):
    salary_base: float = Field(ge=0)
    has_periculosidade: bool = False
    has_adicional_dirigida: bool = False
    extra_hours_50: float = Field(default=0, ge=0)
    extra_hours_70: float = Field(default=0, ge=0)
    extra_hours_100: float = Field(default=0, ge=0)
    additional_costs: float | None = Field(default=None, ge=0)
    year: int = Field(..., ge=2000, le=2100)
    month: int = Field(..., ge=1, le=12)


class CLTCostPreviewResponse(BaseModel):
    total_cost: float
    business_days: int
    reference_month: date


class EmployeeAllocationRead(UUIDTimestampRead):
    employee_id: UUID
    project_id: UUID
    start_date: date
    end_date: date | None = None
    allocation_percent: float
    monthly_cost: float | None = None
    hours_allocated: float | None = None


class EmployeeAllocationCreate(BaseModel):
    employee_id: UUID
    project_id: UUID
    start_date: date
    end_date: date | None = None
    allocation_percent: float = Field(default=100, ge=0, le=100)
    monthly_cost: float | None = Field(default=None, ge=0)
    hours_allocated: float | None = Field(default=None, ge=0)
