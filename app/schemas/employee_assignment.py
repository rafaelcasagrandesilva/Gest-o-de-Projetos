"""Schemas da Alocação contratual do colaborador.

Valores monetários são `float | None`: `None` = omitido por Dados sensíveis (`employees.sensitive`),
nunca zero — mesma convenção do resto do sistema.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.employee_assignment import AllocationType, AssignmentStatus
from app.schemas.common import ORMModel


class EmployeeAssignmentBase(BaseModel):
    project_id: UUID | None = None
    cost_center: str | None = Field(default=None, max_length=255)
    # Padrão INDEPENDENTE: é o caso da esmagadora maioria (hoje 468 das 510 linhas estão a 100%).
    allocation_type: AllocationType = AllocationType.INDEPENDENTE
    role_title: str | None = Field(default=None, max_length=255)
    salary_base: float | None = None
    allowance: float | None = None
    hours_per_month: float | None = None
    employment_type: str | None = Field(default=None, max_length=10)
    # Ignorado quando o tipo é INDEPENDENTE (o serviço força 100).
    allocation_percent: float | None = Field(default=None, ge=0, le=100)
    start_date: date | None = None
    end_date: date | None = None
    notes: str | None = None


class EmployeeAssignmentCreate(EmployeeAssignmentBase):
    pass


class EmployeeAssignmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID | None = None
    cost_center: str | None = Field(default=None, max_length=255)
    allocation_type: AllocationType | None = None
    role_title: str | None = Field(default=None, max_length=255)
    salary_base: float | None = None
    allowance: float | None = None
    hours_per_month: float | None = None
    employment_type: str | None = Field(default=None, max_length=10)
    allocation_percent: float | None = Field(default=None, ge=0, le=100)
    start_date: date | None = None
    end_date: date | None = None
    notes: str | None = None


class EmployeeAssignmentRead(ORMModel, EmployeeAssignmentBase):
    id: UUID
    employee_id: UUID
    status: AssignmentStatus
    # Preenchidos só quando CANCELADA. O motivo fica na auditoria, não aqui.
    cancelled_at: datetime | None = None
    allocation_percent: float
    is_backfilled: bool = False
    # Desnormalizado: a tela lista alocações sem precisar buscar cada projeto.
    project_name: str | None = None


class EmployeeAssignmentClose(BaseModel):
    """Encerramento: nunca exclui, só carimba o fim."""

    end_date: date | None = None


class EmployeeAssignmentCancel(BaseModel):
    """Cancelamento (engano, sem efeito financeiro). O motivo vai para a auditoria."""

    reason: str | None = Field(default=None, max_length=500)
