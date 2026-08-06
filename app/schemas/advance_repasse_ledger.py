from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class RepasseLedgerEntryRead(ORMModel):
    id: UUID
    institution_id: UUID
    direction: str  # CREDIT | DEBIT
    amount: float
    source_type: str  # OPERATION | SETTLEMENT | ADJUSTMENT
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
