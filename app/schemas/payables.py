from __future__ import annotations

from datetime import date, datetime
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
    include_in_dashboard: bool = True
    # Reconciliação: lançamento automático cuja origem foi removida (resíduo).
    is_obsolete: bool = False
    obsolete_reason: str | None = None
    reconciled_at: datetime | None = None
    status: PayableSnapshotStatus
    last_payment_date: date | None = None
    # Valor pago com payment_date no mês da listagem (fluxo de caixa do período).
    paid_in_period: float = 0.0
    # Competência da obrigação fora do mês filtrado na tela operacional.
    competence_out_of_view: bool = False


class PayableSnapshotRegisterPaymentBody(BaseModel):
    amount: float = Field(..., gt=0)
    payment_date: date | None = Field(
        None,
        description="Data real do pagamento (fluxo de caixa). Padrão: hoje.",
    )
    observation: str | None = Field(None, max_length=2000)
    allow_overpayment: bool = False

    @field_validator("payment_date")
    @classmethod
    def payment_date_not_future(cls, v: date | None) -> date | None:
        if v is not None and v > date.today():
            raise ValueError("Data do pagamento não pode ser futura.")
        return v


class PayableSnapshotReversePaymentBody(BaseModel):
    amount: float = Field(..., gt=0)
    reversal_reason: str | None = Field(None, max_length=500)
    observation: str | None = Field(None, max_length=2000)


# Compatibilidade com clientes antigos (sem payment_date).
class PayableSnapshotPaymentBody(BaseModel):
    amount: float = Field(..., gt=0)
    observation: str | None = Field(None, max_length=2000)


class PayableSnapshotUpdate(BaseModel):
    amount_final: float | None = Field(None, gt=0)
    due_date: date | None = None
    observation: str | None = Field(None, max_length=4000)
    include_in_dashboard: bool | None = None


class PayableSnapshotManualCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    amount: float = Field(..., gt=0)
    due_date: date
    category: str = Field(..., min_length=1, max_length=120)
    cost_center: str = Field(..., min_length=1, max_length=255)
    month: date = Field(..., description="Mês de competência do pagamento (YYYY-MM-01).")
    include_in_dashboard: bool = True

    @field_validator("month")
    @classmethod
    def normalize_month(cls, v: date) -> date:
        return normalize_competencia(v)


class PayableSnapshotReconcileResult(BaseModel):
    """Resumo da reconciliação de um snapshot mensal."""

    month: date
    checked: int = Field(..., description="Lançamentos automáticos rastreáveis avaliados.")
    marked_obsolete: int = Field(..., description="Marcados como obsoletos nesta execução.")
    cleared: int = Field(..., description="Reativados (origem voltou a existir).")
    obsolete_total: int = Field(..., description="Total de linhas obsoletas no mês após a reconciliação.")


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

