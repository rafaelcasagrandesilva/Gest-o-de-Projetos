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
    description: str | None = None
