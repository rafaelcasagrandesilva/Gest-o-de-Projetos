from __future__ import annotations

from datetime import date, timedelta
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.receivable import DUE_DAYS_CHOICES

INVOICE_STATUSES = frozenset({"EMITIDA", "ANTECIPADA", "RECEBIDA", "CANCELADA"})
from app.schemas.common import UUIDTimestampRead
from app.schemas.receivable_advance_batch import AdvanceBatchSummaryRead

InvoiceStatus = Literal["EMITIDA", "ANTECIPADA", "RECEBIDA", "CANCELADA"]

CENT_TOL = 0.009
ADV_TOL = 0.0001


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
        return "RECEBIDA"
    if is_anticipated:
        return "ANTECIPADA"
    return "EMITIDA"


class ReceivableInvoiceFileRead(UUIDTimestampRead):
    invoice_id: UUID
    file_name: str
    content_type: str
    size_bytes: int


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
    advance_amount_received: float | None = None
    advance_amount_due: float | None = None
    advance_due_date: date | None = None
    anticipations: list["InvoiceAnticipationRead"] = Field(default_factory=list)
    received_amount: float
    received_date: date | None = None
    interest_amount: float
    advance_cost_value: float | None = None
    advance_interest_rate: float | None = None
    advance_monthly_rate: float | None = None
    implied_monthly_rate_percent: float | None = None
    status: InvoiceStatus
    has_pdf: bool = False
    pdf_url: str | None = None
    pdf_files: list[ReceivableInvoiceFileRead] = Field(default_factory=list)
    activity_log: str | None = None
    advance_batch_id: UUID | None = None
    advance_batch: AdvanceBatchSummaryRead | None = None


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
    advance_amount_received: float | None = Field(None, gt=0)
    advance_amount_due: float | None = Field(None, gt=0)
    advance_due_date: date | None = None
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

    @model_validator(mode="after")
    def anticipated_fields_consistent(self) -> ReceivableInvoiceUpdate:
        # Validação parcial: quando explicitamente marcando antecipada, exigir campos completos.
        if self.is_anticipated is True:
            if self.advance_amount_received is None or self.advance_amount_due is None or self.advance_due_date is None:
                raise ValueError(
                    "Para NF antecipada, informe: advance_amount_received, advance_amount_due e advance_due_date."
                )
            if self.advance_amount_due + ADV_TOL < self.advance_amount_received:
                raise ValueError("advance_amount_due deve ser maior ou igual a advance_amount_received.")
        # Se explicitamente desmarcando antecipada, limpar campos é permitido (nullable).
        return self


class InvoiceAnticipationRead(UUIDTimestampRead):
    invoice_id: UUID
    institution: str
    amount_received: float
    amount_to_repay: float
    data_recebimento: date
    due_date: date
    juros_total: float | None = None
    taxa_percentual: float | None = None
    taxa_mensal: float | None = None
    dias: int | None = None


class InvoiceAnticipationCreate(BaseModel):
    institution: str = Field(..., min_length=1, max_length=255)
    amount_received: float = Field(..., gt=0)
    amount_to_repay: float = Field(..., gt=0)
    data_recebimento: date
    due_date: date

    @model_validator(mode="after")
    def ok(self) -> "InvoiceAnticipationCreate":
        if self.amount_to_repay + ADV_TOL < self.amount_received:
            raise ValueError("amount_to_repay deve ser maior ou igual a amount_received.")
        return self


class InvoiceAnticipationUpdate(BaseModel):
    institution: str = Field(..., min_length=1, max_length=255)
    amount_received: float = Field(..., gt=0)
    amount_to_repay: float = Field(..., gt=0)
    data_recebimento: date
    due_date: date = Field(..., alias="repayment_date")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def ok(self) -> "InvoiceAnticipationUpdate":
        if self.amount_to_repay + ADV_TOL < self.amount_received:
            raise ValueError("amount_to_repay deve ser maior ou igual a amount_received.")
        return self


class ReceivableKpisRead(BaseModel):
    total_a_receber: float
    total_bruto_a_receber: float
    recebido_no_mes: float
    em_atraso_valor: float
    total_nfs: int


ReceivableViewStatus = Literal["ABERTO", "PARCIAL", "RECEBIDO"]
ReceivableViewType = Literal["NF", "MANUAL", "ANTECIPACAO", "BORDERO"]


class ReceivableViewRead(UUIDTimestampRead):
    """Visão de contas a receber (NFs + lançamentos manuais)."""

    tipo: ReceivableViewType = "NF"
    client: str | None = None
    number: str
    descricao: str | None = None
    numero_referencia: str | None = None
    issue_date: date
    due_date: date
    received_at: date | None = None
    net_value: float
    amount_received_advance: float
    amount_received_customer: float
    total_received: float
    remaining: float
    status: ReceivableViewStatus
    observacao: str | None = None


class ReceivableManualItemCreate(BaseModel):
    descricao: str = Field(..., min_length=1, max_length=255)
    cliente: str = Field(..., min_length=1, max_length=255)
    numero_referencia: str | None = Field(default=None, max_length=64)
    data_emissao: date
    data_vencimento: date
    valor_liquido: float = Field(..., gt=0)
    valor_recebido: float | None = Field(default=None, ge=0)
    data_recebimento: date | None = None
    observacao: str | None = None

    @model_validator(mode="after")
    def ok(self) -> "ReceivableManualItemCreate":
        if self.valor_recebido is not None and self.valor_recebido > self.valor_liquido + CENT_TOL:
            raise ValueError("valor_recebido não pode ser maior que valor_liquido.")
        if self.data_recebimento is not None and (self.valor_recebido or 0) <= 0:
            raise ValueError("Para informar data_recebimento, informe valor_recebido > 0.")
        return self


class ReceivableManualItemUpdate(BaseModel):
    descricao: str | None = Field(default=None, min_length=1, max_length=255)
    cliente: str | None = Field(default=None, min_length=1, max_length=255)
    numero_referencia: str | None = Field(default=None, max_length=64)
    data_emissao: date | None = None
    data_vencimento: date | None = None
    valor_liquido: float | None = Field(default=None, gt=0)
    valor_recebido: float | None = Field(default=None, ge=0)
    data_recebimento: date | None = None
    observacao: str | None = None

    @model_validator(mode="after")
    def ok(self) -> "ReceivableManualItemUpdate":
        # validação cruzada completa é feita no service (precisa do valor_liquido final)
        if self.data_recebimento is not None and (self.valor_recebido or 0) <= 0:
            raise ValueError("Para informar data_recebimento, informe valor_recebido > 0.")
        return self


class ReceivableManualItemRead(UUIDTimestampRead):
    workspace_id: str
    descricao: str
    cliente: str
    numero_referencia: str | None = None
    data_emissao: date
    data_vencimento: date
    valor_liquido: float
    valor_recebido: float
    data_recebimento: date | None = None
    observacao: str | None = None
    status: ReceivableViewStatus
