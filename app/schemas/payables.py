from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import UUIDTimestampRead
from app.utils.date_utils import normalize_competencia

PayableStatus = Literal["ABERTO", "PAGO", "ATRASADO"]

PayableSnapshotType = Literal[
    "COLLABORATOR",
    "VEHICLE",
    "FIXED_COST",
    "ENDIVIDAMENTO",
    # Valor legado mantido para compatibilidade durante/antes da migration.
    "FINANCIAL",
    "MANUAL",
    "ANTECIPACAO",
]

PayableSnapshotStatus = Literal["ABERTO", "PARCIAL", "PAGO"]


class PayableSnapshotRead(UUIDTimestampRead):
    month: date
    type: PayableSnapshotType
    ref_id: UUID | None = None
    project_id: UUID | None = None

    name: str
    cost_center: str
    category: str

    amount_original: float
    amount_final: float
    amount_paid: float
    amount_remaining: float
    is_overpaid: bool = False
    overpaid_amount: float = 0.0

    due_date: date
    payment_date: date | None
    paid: bool

    observation: str | None = None
    status: PayableSnapshotStatus


class PayableSnapshotPaymentBody(BaseModel):
    amount: float = Field(..., gt=0)
    observation: str | None = Field(None, max_length=2000)


class PayableSnapshotUpdate(BaseModel):
    amount_final: float | None = Field(None, gt=0)
    due_date: date | None = None
    observation: str | None = Field(None, max_length=4000)


class PayableSnapshotManualCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    amount: float = Field(..., gt=0)
    due_date: date
    category: str = Field(..., min_length=1, max_length=120)
    cost_center: str = Field(..., min_length=1, max_length=255)
    month: date = Field(..., description="Mês de competência do pagamento (YYYY-MM-01).")

    @field_validator("month")
    @classmethod
    def normalize_month(cls, v: date) -> date:
        return normalize_competencia(v)


class PayableCreate(BaseModel):
    description: str = Field(..., min_length=1, max_length=255)
    supplier_name: str = Field(..., min_length=1, max_length=255)
    amount: float = Field(..., gt=0)
    due_date: date
    competence: date = Field(..., description="Competência (mês referência). Usar qualquer dia; será normalizado.")
    chart_account_id: UUID
    cost_center: str | None = Field(None, max_length=255)
    project_id: UUID | None = None

    @field_validator("competence")
    @classmethod
    def normalize_comp(cls, v: date) -> date:
        return normalize_competencia(v)


class PayableUpdate(BaseModel):
    description: str | None = Field(None, min_length=1, max_length=255)
    supplier_name: str | None = Field(None, min_length=1, max_length=255)
    amount: float | None = Field(None, gt=0)
    due_date: date | None = None
    competence: date | None = None
    chart_account_id: UUID | None = None
    cost_center: str | None = Field(None, max_length=255)
    project_id: UUID | None = None

    @field_validator("competence")
    @classmethod
    def normalize_comp(cls, v: date | None) -> date | None:
        return normalize_competencia(v) if v is not None else None


class PayableRead(UUIDTimestampRead):
    description: str
    supplier_name: str
    amount: float
    due_date: date
    payment_date: date | None
    competence: date

    chart_account_id: UUID
    chart_account_code: str
    chart_account_name: str
    chart_account_type: str

    cost_center: str | None = None
    project_id: UUID | None = None
    project_name: str | None = None

    status: PayableStatus


class PayablePay(BaseModel):
    payment_date: date = Field(..., description="Data do pagamento.")

