from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class RepasseLedgerEntryRead(ORMModel):
    id: UUID
    institution_id: UUID
    direction: str  # CREDIT | DEBIT
    amount: float
    source_type: str  # OPERATION | SETTLEMENT | WITHDRAWAL | ADJUSTMENT
    withdrawal_purpose: str | None = None  # DEBT_REDUCTION | OTHER (só em WITHDRAWAL)
    #: Dívida abatida por esta retirada (só em DEBT_REDUCTION). Vira pagamento na Evolução.
    debt_item_id: UUID | None = None
    source_batch_id: UUID | None = None
    source_movement_id: UUID | None = None
    occurred_at: date
    description: str | None = None
    reversed_at: datetime | None = None
    reversal_reason: str | None = None
    created_at: datetime


class RepasseLedgerStatementRead(BaseModel):
    institution_id: UUID | None = None
    balance: float
    entries: list[RepasseLedgerEntryRead] = Field(default_factory=list)


class RepasseWithdrawalCreate(BaseModel):
    """Entrada da Retirada de Repasse — destino ESTRUTURADO; descrição é só observação livre."""

    institution_id: UUID
    amount: float = Field(gt=0)
    occurred_at: date
    purpose: Literal["DEBT_REDUCTION", "OTHER"]
    #: Qual dívida a retirada abate. Só faz sentido com purpose=DEBT_REDUCTION; sem ele a
    #: retirada apenas reduz o saldo do repasse, sem virar pagamento de dívida nenhuma.
    debt_item_id: UUID | None = None
    description: str | None = None


class RepasseDebtLinkIn(BaseModel):
    """Vincula/desvincula uma retirada à dívida que ela abate. `null` desvincula."""

    debt_item_id: UUID | None = None
