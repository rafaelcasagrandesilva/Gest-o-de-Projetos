from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import UUIDTimestampRead

AdvanceBatchStatus = Literal["DRAFT", "OPEN", "SETTLED", "CANCELLED"]
AdvanceOperationType = Literal["BORDERO", "FACTORING", "FIDC", "OUTROS"]
# Base de antecipação por NF. BRUTO/LIQUIDO/LIQUIDO_MENOS_10 (Lepta); MANUAL (Daycoval).
AdvanceBasis = Literal["BRUTO", "LIQUIDO", "LIQUIDO_MENOS_10", "MANUAL"]


class AdvanceBatchItemInput(BaseModel):
    invoice_id: UUID
    advance_basis: AdvanceBasis | None = None
    advanced_amount: float | None = Field(default=None, ge=0)


class AdvanceOperationSummaryRead(BaseModel):
    """Resumo curto de uma operação para indicadores de histórico N:N (regras 4 e 6)."""

    id: UUID
    sgc_number: int | None = None
    batch_number: str
    institution: str
    status: AdvanceBatchStatus


class AdvanceOperationHistoryRead(AdvanceOperationSummaryRead):
    """Item do HISTÓRICO DE ANTECIPAÇÕES da NF (regra 5)."""

    receive_date: date | None = None
    repayment_date: date | None = None
    # Valor antecipado da NF nesta operação (congelado no item).
    advanced_amount: float | None = None
    # Valor realizado da operação, quando informado.
    received_amount: float | None = None


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
    # Histórico N:N (regra 4): operações válidas em que a NF já participou. Permite
    # exibir "Já usada em N operações • LEPTA • DAYCOVAL" sem sumir da seleção.
    operations_count: int = 0
    operations: list[AdvanceOperationSummaryRead] = Field(default_factory=list)


class AdvanceBatchItemRead(UUIDTimestampRead):
    batch_id: UUID
    invoice_id: UUID
    invoice_amount: float
    advance_basis: str | None = None
    advanced_amount: float | None = None
    invoice_number: str | None = None
    client_name: str | None = None
    project_name: str | None = None
    competence_month: date | None = None
    gross_amount: float | None = None
    net_amount: float | None = None
    issue_date: date | None = None
    due_date: date | None = None
    invoice_status: str | None = None
    # Regra 6: outras operações válidas em que esta mesma NF participa (com links).
    other_operations: list[AdvanceOperationSummaryRead] = Field(default_factory=list)


class AdvanceBatchRead(UUIDTimestampRead):
    # Número interno do SGC: identificador operacional oficial (sequência 1, 2, 3, …).
    sgc_number: int
    batch_number: str
    operation_type: AdvanceOperationType = "BORDERO"
    operation_code: str | None = None
    institution: str
    institution_id: UUID | None = None
    institution_profile: str | None = None
    gross_amount: float
    received_amount: float
    expected_amount: float | None = None
    actual_received_amount: float | None = None
    discount_amount: float
    fee_amount: float
    repasse_enabled: bool = False
    repasse_amount: float | None = None
    receive_date: date
    repayment_date: date
    confirmed_at: datetime | None = None
    observation: str | None = None
    include_in_dashboard: bool = True
    status: AdvanceBatchStatus
    created_by_id: UUID | None = None
    items: list[AdvanceBatchItemRead] = Field(default_factory=list)
    invoice_count: int = 0
    discount_percent: float | None = None
    # Indicador informativo do custo efetivo da antecipação (não afeta CAR/CAP/Dashboard).
    invoices_net_total: float | None = None
    finance_cost_amount: float | None = None
    finance_cost_percent: float | None = None


class AdvanceBatchCreate(BaseModel):
    operation_type: AdvanceOperationType = "BORDERO"
    operation_code: str | None = Field(default=None, max_length=64)
    institution_id: UUID
    received_amount: float = Field(default=0, ge=0)
    discount_amount: float = Field(default=0, ge=0)
    fee_amount: float = Field(default=0, ge=0)
    repasse_enabled: bool = False
    receive_date: date
    # Opcional: perfis sem devolução (ex.: Daycoval) não a informam.
    repayment_date: date | None = None
    observation: str | None = None
    # Conjunto de NFs: simples (invoice_ids) ou estruturado por NF (items, com base/valor).
    invoice_ids: list[UUID] = Field(default_factory=list)
    items: list[AdvanceBatchItemInput] = Field(default_factory=list)

    @field_validator("operation_code")
    @classmethod
    def strip_code(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s or None

    @model_validator(mode="after")
    def dates_ok(self) -> AdvanceBatchCreate:
        # Sem validação de devolução quando ela não é informada (perfis sem devolução).
        if self.repayment_date is not None and self.repayment_date < self.receive_date:
            raise ValueError("A data de devolução não pode ser anterior à data de recebimento.")
        return self

    @model_validator(mode="after")
    def has_invoices(self) -> AdvanceBatchCreate:
        if len(self.invoice_ids) + len(self.items) < 1:
            raise ValueError("Selecione ao menos 1 nota fiscal para a operação.")
        return self


class AdvanceBatchUpdate(BaseModel):
    include_in_dashboard: bool | None = None
    # Valor efetivamente recebido (realizado) — perfis com previsto×realizado (Daycoval).
    actual_received_amount: float | None = Field(default=None, ge=0)


class AdvanceBatchSummaryRead(BaseModel):
    """Resumo discreto para exibição na NF (seção Antecipações, somente leitura)."""

    id: UUID
    sgc_number: int | None = None
    batch_number: str
    institution: str
    status: AdvanceBatchStatus
    receive_date: date | None = None
    repayment_date: date | None = None
    received_amount: float | None = None
    gross_amount: float | None = None
