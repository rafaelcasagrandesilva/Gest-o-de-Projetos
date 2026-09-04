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
    # Quando ligado, o cálculo usa `nf_amount` no lugar de `amount`. O valor manual nunca é
    # sobrescrito: desligar devolve exatamente o número que o gestor informou.
    use_nf_amount: bool = False
    # Soma do BRUTO das NFs FATURADAS da mesma competência do projeto (pré-faturada e
    # cancelada ficam de fora). NÃO vem do banco — é preenchido pelo endpoint de listagem,
    # que consulta as notas. `None` = não conferido (ou redigido por Dados sensíveis).
    nf_amount: float | None = None

    @computed_field
    @property
    def effective_amount(self) -> float | None:
        """O valor que o Dashboard realmente usa nesta linha."""
        if self.use_nf_amount and self.nf_amount is not None:
            return self.nf_amount
        return self.amount

    @computed_field
    @property
    def retention_value(self) -> float | None:
        # Null-safe: quando o valor é redigido (None), a retenção também fica oculta (None).
        # A base acompanha a fonte escolhida — em modo NF os 10% incidem sobre a soma faturada,
        # e não sobre o valor manual, senão receita e retenção viriam de origens diferentes.
        base = self.effective_amount
        if base is None:
            return None
        return revenue_retention_value(amount=base, has_retention=self.has_retention)


class RevenueCreate(BaseModel):
    project_id: UUID
    competencia: date
    amount: float = Field(gt=0)
    description: str | None = Field(default=None, max_length=255)
    status: Literal["previsto", "recebido"] = "recebido"
    has_retention: bool = False
    use_nf_amount: bool = False
    scenario: str | None = Field(default=None, description="PREVISTO ou REALIZADO")


class RevenueUpdate(BaseModel):
    amount: float | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, max_length=255)
    competencia: date | None = None
    status: Literal["previsto", "recebido"] | None = None
    has_retention: bool | None = None
    use_nf_amount: bool | None = None


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
