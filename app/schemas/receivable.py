from __future__ import annotations

from datetime import date, timedelta
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.receivable import DUE_DAYS_CHOICES

INVOICE_STATUSES = frozenset({"EMITIDA", "ANTECIPADA", "FINALIZADA", "CANCELADA"})
from app.schemas.common import UUIDTimestampRead

InvoiceStatus = Literal["EMITIDA", "ANTECIPADA", "FINALIZADA", "CANCELADA"]

CENT_TOL = 0.009


def compute_due_date(issue_date: date, due_days: int) -> date:
    return issue_date + timedelta(days=due_days)


def compute_interest_amount(*, is_anticipated: bool, net_amount: float, received_amount: float) -> float:
    if not is_anticipated:
        return 0.0
    return max(0.0, float(net_amount) - float(received_amount))


def compute_implied_monthly_rate_percent(*, gross_amount: float, net_amount: float) -> float | None:
    """Indicador somente leitura: desconto implícito (bruto → líquido), em %."""
    g = float(gross_amount)
    if g <= 0:
        return None
    return round((g - float(net_amount)) / g * 100.0, 4)


def derive_invoice_status(
    *,
    stored_status: str,
    is_anticipated: bool,
    received_amount: float,
    net_amount: float,
) -> str:
    if stored_status == "CANCELADA":
        return "CANCELADA"
    if received_amount >= float(net_amount) - CENT_TOL:
        return "FINALIZADA"
    if is_anticipated:
        return "ANTECIPADA"
    return "EMITIDA"


class ReceivableInvoiceRead(UUIDTimestampRead):
    project_id: UUID
    project_name: str | None = None
    number: str
    issue_date: date
    due_days: int
    due_date: date
    gross_amount: float
    net_amount: float
    client_name: str | None = None
    notes: str | None = None
    is_anticipated: bool
    institution: str | None = None
    received_amount: float
    received_date: date | None = None
    interest_amount: float
    implied_monthly_rate_percent: float | None = None
    status: InvoiceStatus
    has_pdf: bool = False
    pdf_url: str | None = None
    activity_log: str | None = None


class ReceivableInvoiceCreate(BaseModel):
    project_id: UUID
    number: str = Field(..., min_length=1, max_length=64)
    issue_date: date
    due_days: int = Field(..., description="Prazo em dias: 30, 60 ou 90")
    gross_amount: float = Field(gt=0)
    net_amount: float | None = Field(default=None, gt=0)
    client_name: str | None = Field(None, max_length=512)
    notes: str | None = None

    @field_validator("due_days")
    @classmethod
    def due_days_ok(cls, v: int) -> int:
        if v not in DUE_DAYS_CHOICES:
            raise ValueError("due_days deve ser 30, 60 ou 90.")
        return v


class ReceivableInvoiceUpdate(BaseModel):
    number: str | None = Field(None, min_length=1, max_length=64)
    issue_date: date | None = None
    due_days: int | None = None
    gross_amount: float | None = Field(None, gt=0)
    net_amount: float | None = Field(None, gt=0)
    client_name: str | None = Field(None, max_length=512)
    notes: str | None = None
    is_anticipated: bool | None = None
    institution: str | None = Field(None, max_length=255)
    received_amount: float | None = Field(None, ge=0)
    received_date: date | None = None
    status: InvoiceStatus | None = Field(None, description="Use CANCELADA para cancelar manualmente.")

    @field_validator("due_days")
    @classmethod
    def due_days_ok(cls, v: int | None) -> int | None:
        if v is None:
            return None
        if v not in DUE_DAYS_CHOICES:
            raise ValueError("due_days deve ser 30, 60 ou 90.")
        return v

    @model_validator(mode="after")
    def status_ok(self) -> ReceivableInvoiceUpdate:
        if self.status is not None and self.status not in INVOICE_STATUSES:
            raise ValueError("status inválido.")
        return self


class ReceivableKpisRead(BaseModel):
    total_a_receber: float
    recebido_no_mes: float
    em_atraso_valor: float
    total_nfs: int
