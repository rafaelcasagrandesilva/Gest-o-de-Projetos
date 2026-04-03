from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampRead


StatusNF = Literal["PAGA", "PENDENTE", "ATRASADA"]


def compute_nf_status(*, today: date, vencimento: date, saldo: float) -> StatusNF:
    if saldo <= 0:
        return "PAGA"
    if today > vencimento:
        return "ATRASADA"
    return "PENDENTE"


class ReceivableInvoicePaymentRead(UUIDTimestampRead):
    invoice_id: UUID
    data_recebimento: date
    valor: float


class ReceivableInvoicePaymentCreate(BaseModel):
    data_recebimento: date
    valor: float = Field(gt=0)


class ReceivableInvoiceRead(UUIDTimestampRead):
    project_id: UUID
    project_name: str | None = None
    numero_nf: str
    data_emissao: date
    valor_bruto: float
    vencimento: date
    data_prevista_pagamento: date | None = None
    numero_pedido: str | None = None
    numero_conformidade: str | None = None
    observacao: str | None = None
    antecipada: bool
    instituicao: str | None = None
    taxa_juros_mensal: float | None = None
    total_recebido: float
    saldo: float
    status: StatusNF


class ReceivableInvoiceCreate(BaseModel):
    project_id: UUID
    numero_nf: str = Field(..., min_length=1, max_length=64)
    data_emissao: date
    valor_bruto: float = Field(gt=0)
    vencimento: date
    data_prevista_pagamento: date | None = None
    numero_pedido: str | None = Field(None, max_length=128)
    numero_conformidade: str | None = Field(None, max_length=128)
    observacao: str | None = None
    antecipada: bool = False
    instituicao: str | None = Field(None, max_length=255)
    taxa_juros_mensal: float | None = Field(None, ge=0)


class ReceivableInvoiceUpdate(BaseModel):
    numero_nf: str | None = Field(None, min_length=1, max_length=64)
    data_emissao: date | None = None
    valor_bruto: float | None = Field(None, gt=0)
    vencimento: date | None = None
    data_prevista_pagamento: date | None = None
    numero_pedido: str | None = Field(None, max_length=128)
    numero_conformidade: str | None = Field(None, max_length=128)
    observacao: str | None = None
    antecipada: bool | None = None
    instituicao: str | None = Field(None, max_length=255)
    taxa_juros_mensal: float | None = Field(None, ge=0)


class ReceivableKpisRead(BaseModel):
    total_a_receber: float
    recebido_no_mes: float
    em_atraso_valor: float
    total_nfs: int
