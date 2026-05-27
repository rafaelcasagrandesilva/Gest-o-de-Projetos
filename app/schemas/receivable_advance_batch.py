from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import UUIDTimestampRead

AdvanceBatchStatus = Literal["OPEN", "SETTLED", "CANCELLED"]
AdvanceOperationType = Literal["BORDERO", "FACTORING", "FIDC", "OUTROS"]


class AdvanceBatchEligibleInvoiceRead(BaseModel):
    id: UUID
    project_id: UUID
    project_name: str | None = None
    number: str
    client_name: str | None = None
    issue_date: date
    due_date: date
    gross_amount: float
    net_amount: float
    status: str


class AdvanceBatchItemRead(UUIDTimestampRead):
    batch_id: UUID
    invoice_id: UUID
    invoice_amount: float
    invoice_number: str | None = None
    client_name: str | None = None
    project_name: str | None = None
    issue_date: date | None = None
    due_date: date | None = None


class AdvanceBatchRead(UUIDTimestampRead):
    batch_number: str
    operation_type: AdvanceOperationType = "BORDERO"
    operation_code: str | None = None
    institution: str
    gross_amount: float
    received_amount: float
    discount_amount: float
    fee_amount: float
    receive_date: date
    repayment_date: date
    observation: str | None = None
    status: AdvanceBatchStatus
    created_by_id: UUID | None = None
    items: list[AdvanceBatchItemRead] = Field(default_factory=list)
    invoice_count: int = 0
    discount_percent: float | None = None


class AdvanceBatchCreate(BaseModel):
    operation_type: AdvanceOperationType = "BORDERO"
    operation_code: str | None = Field(default=None, max_length=64)
    institution: str = Field(..., min_length=1, max_length=255)
    received_amount: float = Field(..., ge=0)
    discount_amount: float = Field(default=0, ge=0)
    fee_amount: float = Field(default=0, ge=0)
    receive_date: date
    repayment_date: date
    observation: str | None = None
    invoice_ids: list[UUID] = Field(..., min_length=2)

    @field_validator("institution")
    @classmethod
    def strip_institution(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Informe a instituição.")
        return s

    @field_validator("operation_code")
    @classmethod
    def strip_code(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s or None

    @model_validator(mode="after")
    def dates_ok(self) -> AdvanceBatchCreate:
        if self.repayment_date < self.receive_date:
            raise ValueError("A data de devolução não pode ser anterior à data de recebimento.")
        return self


class AdvanceBatchSummaryRead(BaseModel):
    """Resumo discreto para exibição na NF."""

    id: UUID
    batch_number: str
    institution: str
    status: AdvanceBatchStatus
