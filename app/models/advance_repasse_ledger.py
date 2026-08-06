from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampUUIDMixin


class RepasseLedgerDirection(str, enum.Enum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"


class RepasseLedgerSource(str, enum.Enum):
    """De onde veio um lançamento — metadado GENÉRICO de rastreio.

    O Ledger não interpreta essas origens (não conhece LEPTA/borderô); são apenas rótulos
    para auditoria/estorno. `OPERATION` = crédito nascido de uma operação de antecipação;
    `SETTLEMENT` = débito nascido de uma movimentação de liquidação; `ADJUSTMENT` = ajuste
    manual/migração.
    """

    OPERATION = "OPERATION"
    SETTLEMENT = "SETTLEMENT"
    ADJUSTMENT = "ADJUSTMENT"


REPASSE_LEDGER_DIRECTION_DB = Enum(RepasseLedgerDirection, name="repasse_ledger_direction")
REPASSE_LEDGER_SOURCE_DB = Enum(RepasseLedgerSource, name="repasse_ledger_source")


class AdvanceRepasseLedgerEntry(TimestampUUIDMixin, Base):
    """Lançamento do Extrato (Ledger) de Repasse — append-only, por instituição.

    Livro-razão genérico e INDEPENDENTE do módulo de Antecipações: registra apenas créditos
    e débitos. Saldo por instituição = Σ CREDIT − Σ DEBIT dos lançamentos ATIVOS
    (`reversed_at IS NULL`). Nunca é editado nem excluído — só estornado por lançamento.

    Os campos `source_*` são metadados de rastreio (o Ledger não os interpreta): quem decide
    creditar/debitar (o fluxo de Antecipações) preenche a origem para permitir auditoria e
    estorno idempotente.
    """

    __tablename__ = "advance_repasse_ledger"

    institution_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("advance_institutions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    direction: Mapped[RepasseLedgerDirection] = mapped_column(
        REPASSE_LEDGER_DIRECTION_DB, nullable=False, index=True
    )
    # Sempre positivo; o sinal é dado por `direction`.
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    source_type: Mapped[RepasseLedgerSource] = mapped_column(
        REPASSE_LEDGER_SOURCE_DB, nullable=False, index=True
    )
    # Origem rastreável (opcional): operação (CREDIT) ou movimentação de liquidação (DEBIT).
    source_batch_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("receivable_advance_batches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_movement_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("advance_settlement_movements.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    occurred_at: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    reversal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
