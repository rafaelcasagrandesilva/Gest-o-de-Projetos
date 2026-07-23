from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, computed_field

from app.schemas.common import UUIDTimestampRead
from app.services.financial_crud_service import revenue_retention_value


class RevenueRead(UUIDTimestampRead):
    project_id: UUID
    competencia: date
    scenario: str = "REALIZADO"
    # Optional para redação (Dados sensíveis). Sem `billing.sensitive`, backend omite (None).
    amount: float | None = None
    description: str | None = None
    status: str
    has_retention: bool

    @computed_field
    @property
    def retention_value(self) -> float | None:
        # Null-safe: quando `amount` é redigido (None), a retenção também fica oculta (None).
        # Para quem tem sensitive, o valor é idêntico ao anterior (cálculo inalterado).
        if self.amount is None:
            return None
        return revenue_retention_value(amount=self.amount, has_retention=self.has_retention)


class RevenueCreate(BaseModel):
    project_id: UUID
    competencia: date
    amount: float = Field(gt=0)
    description: str | None = Field(default=None, max_length=255)
    status: Literal["previsto", "recebido"] = "recebido"
    has_retention: bool = False
    scenario: str | None = Field(default=None, description="PREVISTO ou REALIZADO")


class RevenueUpdate(BaseModel):
    amount: float | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, max_length=255)
    competencia: date | None = None
    status: Literal["previsto", "recebido"] | None = None
    has_retention: bool | None = None


class InvoiceRead(UUIDTimestampRead):
    project_id: UUID
    competencia: date
    amount: float | None = None  # Optional para redação (Dados sensíveis).
    due_date: date
    status: str
    supplier: str | None = None
    description: str | None = None


class InvoiceCreate(BaseModel):
    project_id: UUID
    competencia: date
    amount: float = Field(gt=0)
    due_date: date
    supplier: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=255)


class InvoiceUpdate(BaseModel):
    amount: float | None = Field(default=None, gt=0)
    due_date: date | None = None
    status: str | None = Field(default=None, max_length=30)
    supplier: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=255)


class InvoiceAnticipationRead(UUIDTimestampRead):
    invoice_id: UUID
    anticipated_at: date
    fee_amount: float | None = None  # Optional para redação (Dados sensíveis).
    notes: str | None = None


class InvoiceAnticipationCreate(BaseModel):
    invoice_id: UUID
    anticipated_at: date
    fee_amount: float = Field(gt=0)
    notes: str | None = Field(default=None, max_length=255)
