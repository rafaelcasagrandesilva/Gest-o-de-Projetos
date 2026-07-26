from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampRead


class PaymentVariableComponentRead(UUIDTimestampRead):
    type_id: UUID
    type_name: str
    type_code: str
    employee_id: UUID
    competencia: date
    amount: float
    note: str | None
    project_labor_id: UUID | None
    company_financial_item_id: UUID | None


class PaymentVariableComponentCreate(BaseModel):
    type_id: UUID
    amount: float = Field(..., gt=0)
    note: str | None = Field(default=None, max_length=2000)
    # Contexto: exatamente UM. Projeto usa a competência do vínculo; Custo Fixo exige a
    # competência informada (o item não é por competência).
    project_labor_id: UUID | None = None
    company_financial_item_id: UUID | None = None
    competencia: date | None = None


class PaymentVariableComponentUpdate(BaseModel):
    type_id: UUID | None = None
    amount: float | None = Field(default=None, gt=0)
    note: str | None = Field(default=None, max_length=2000)


class VariableComponentItem(BaseModel):
    """Linha da lista enviada no salvamento em lote (id ausente = novo)."""

    id: UUID | None = None
    type_id: UUID
    amount: float = Field(..., gt=0)
    note: str | None = Field(default=None, max_length=2000)


class VariableComponentReplace(BaseModel):
    """Conjunto DESEJADO de componentes de um contexto — reconciliado em 1 transação."""

    items: list[VariableComponentItem] = Field(default_factory=list)
