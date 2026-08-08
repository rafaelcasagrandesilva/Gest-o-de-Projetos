from __future__ import annotations

import enum
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, Enum, ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampUUIDMixin
from app.models.advance_settlement_movement import ADVANCE_FUNDING_SOURCE_DB, AdvanceFundingSource


class SettlementEventCreationSource(str, enum.Enum):
    """Canal pelo qual o evento foi criado — NÃO é a origem financeira (`funding_source`).

    `MANUAL` = liquidação individual pela tela; `MASS` = liquidação em massa. Reservado para
    canais futuros (`BANK_IMPORT`, `CNAB`, `PIX`, `TED`, `ERP`) sem remodelagem — todos
    representam o mesmo ato financeiro (um pagamento que quita 1..N obrigações).
    """

    MANUAL = "MANUAL"
    MASS = "MASS"


class SettlementEventStatus(str, enum.Enum):
    """Estado do evento. Nasce `ACTIVE`; os demais existem para evolução futura (estorno
    parcial/total do evento) SEM nova migration. Nesta entrega, permanece sempre `ACTIVE`."""

    ACTIVE = "ACTIVE"
    PARTIALLY_REVERSED = "PARTIALLY_REVERSED"
    FULLY_REVERSED = "FULLY_REVERSED"


SETTLEMENT_EVENT_CREATION_SOURCE_DB = Enum(
    SettlementEventCreationSource, name="settlement_event_creation_source"
)
SETTLEMENT_EVENT_STATUS_DB = Enum(SettlementEventStatus, name="settlement_event_status")


class AdvanceSettlementEvent(TimestampUUIDMixin, Base):
    """Evento de Liquidação — um **pagamento/liquidação** (evento financeiro) que quita 1..N
    obrigações (participações NF × operação), agnóstico ao canal de origem.

    Fica ACIMA das movimentações (`advance_settlement_movements.event_id`): agrupa N movimentações.
    Cada movimentação continua sendo o grão append-only e a única responsável pelas integrações
    financeiras (Ledger, quando a origem é Saldo do Repasse). **O Evento NÃO referencia o Ledger** —
    a separação Evento → Movimentações → Ledger é intencional e deve ser preservada.

    Registro imutável: `total_amount`/`invoice_count` são snapshots do momento da liquidação. O
    identificador operacional é `number` (sequência) → `code` "LQ-000001" (montado no presenter).
    """

    __tablename__ = "advance_settlement_events"

    # Numeração sequencial (apenas o número); o `code` amigável é derivado no presenter.
    number: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    creation_source: Mapped[SettlementEventCreationSource] = mapped_column(
        SETTLEMENT_EVENT_CREATION_SOURCE_DB, nullable=False, index=True
    )
    status: Mapped[SettlementEventStatus] = mapped_column(
        SETTLEMENT_EVENT_STATUS_DB,
        nullable=False,
        index=True,
        default=SettlementEventStatus.ACTIVE,
    )
    institution_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("advance_institutions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Origem financeira única do evento (mesma enum das movimentações); NULL se multi-origem.
    funding_source: Mapped[AdvanceFundingSource | None] = mapped_column(
        ADVANCE_FUNDING_SOURCE_DB, nullable=True
    )
    # Data PRÓPRIA do pagamento (não derivada das movimentações).
    payment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # Snapshots do momento da liquidação.
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    invoice_count: Mapped[int] = mapped_column(Integer, nullable=False)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
