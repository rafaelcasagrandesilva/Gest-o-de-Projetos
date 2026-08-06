from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampUUIDMixin


class AdvanceFundingSource(str, enum.Enum):
    """Origem dos recursos de UMA movimentação de liquidação.

    É um conceito do módulo de Antecipações (Liquidação), **não** do Ledger — o Ledger
    genérico não conhece origens. Só `SALDO_REPASSE` tem efeito colateral (debita o Ledger);
    as demais são puramente informativas (ex.: `ANTECIPACAO_DAYCOVAL` é apenas um rótulo de
    origem, sem vínculo com nenhuma operação Daycoval específica).
    """

    SALDO_REPASSE = "SALDO_REPASSE"
    RECEBIMENTO_CLIENTE = "RECEBIMENTO_CLIENTE"
    ANTECIPACAO_DAYCOVAL = "ANTECIPACAO_DAYCOVAL"
    CAIXA_EMPRESA = "CAIXA_EMPRESA"
    OUTRA = "OUTRA"


ADVANCE_FUNDING_SOURCE_DB = Enum(AdvanceFundingSource, name="advance_funding_source")

# Rótulos curtos usados na composição de `origens_resumo` (ex.: "Repasse + Caixa").
FUNDING_SOURCE_LABELS: dict[AdvanceFundingSource, str] = {
    AdvanceFundingSource.SALDO_REPASSE: "Repasse",
    AdvanceFundingSource.RECEBIMENTO_CLIENTE: "Cliente",
    AdvanceFundingSource.ANTECIPACAO_DAYCOVAL: "Daycoval",
    AdvanceFundingSource.CAIXA_EMPRESA: "Caixa",
    AdvanceFundingSource.OUTRA: "Outra",
}


class AdvanceSettlementMovement(TimestampUUIDMixin, Base):
    """Movimentação de liquidação de uma obrigação perante a instituição (append-only).

    A obrigação é a **participação** de uma NF numa operação de antecipação
    (`receivable_advance_batch_items`). Ela é liquidada pela **soma** de N movimentações
    ativas — não existe um "registro de liquidação" único (relação 1:N). Cada movimentação
    é um evento imutável (idioma de `PayablePayment`): uma origem, um valor, uma data.
    Nunca é editada nem excluída — só estornada via `reversed_at`.

    A situação da obrigação (EM_ABERTO / PARCIALMENTE_LIQUIDADA / VENCIDA / LIQUIDADA) e os
    totais (valor_total/valor_liquidado/valor_residual) são SEMPRE derivados no backend a
    partir destas movimentações; nunca gravados.
    """

    __tablename__ = "advance_settlement_movements"

    # Obrigação (grão): a participação NF × operação. RESTRICT protege o histórico financeiro
    # (uma participação com movimentação não pode ser removida pelo hard-delete do lote).
    batch_item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("receivable_advance_batch_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Denormalizações para consulta/filtro/rastreio (a fonte é sempre o batch_item).
    batch_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("receivable_advance_batches.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    invoice_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("receivable_invoices.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    institution_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("advance_institutions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Valor DESTA movimentação (parcial). Sempre > 0.
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    funding_source: Mapped[AdvanceFundingSource] = mapped_column(
        ADVANCE_FUNDING_SOURCE_DB, nullable=False, index=True
    )
    settled_at: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Estorno soft: nunca hard-delete (preserva histórico).
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    reversal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
