from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class EmployeeMonthlyPayrollUpsert(BaseModel):
    net_salary_amount: float | None = Field(default=None, ge=0)
    vr_amount: float | None = Field(default=None, ge=0)
    notes: str | None = None


class EmployeeMonthlyPayrollRead(BaseModel):
    id: UUID
    employee_id: UUID
    competence_month: str
    net_salary_amount: float | None
    vr_amount: float | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
