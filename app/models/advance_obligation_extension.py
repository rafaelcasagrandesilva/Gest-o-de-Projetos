from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampUUIDMixin


class AdvanceExtensionRequest(TimestampUUIDMixin, Base):
    """Pedido de prorrogação feito à instituição — uma ou várias NFs para a MESMA nova data.

    A instituição (ex.: Lepta) informa por e-mail o CUSTO do pedido inteiro, pago no dia do
    pedido. Esse custo vira um título no Contas a Pagar (`payable_snapshot_id`, tipo
    Antecipação, centro Financeiro, com a instituição e as NFs na descrição) e entra no custo
    real das antecipações do mês do pagamento. Desfazer só é possível com o título em aberto.
    """

    __tablename__ = "advance_extension_requests"

    institution_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("advance_institutions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    institution_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_due: Mapped[date] = mapped_column(Date, nullable=False)
    cost_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    cost_payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)
    payable_snapshot_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("payable_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    created_by_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AdvanceObligationExtension(TimestampUUIDMixin, Base):
    """Prorrogação do vencimento de UMA obrigação perante a instituição (append-only).

    Vale SÓ para a devolução à instituição: o vencimento da NF com o cliente
    (`receivable_invoices.due_date`) não muda — ele segue sendo o VENCIMENTO ORIGINAL, base do
    cálculo dos juros. O vencimento vigente é o `new_due` da última prorrogação ativa.
    Nunca é editada; desfazer = `reversed_at` (o pedido inteiro, e só se for o mais recente).
    """

    __tablename__ = "advance_obligation_extensions"

    batch_item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("receivable_advance_batch_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    request_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("advance_extension_requests.id", ondelete="CASCADE"), nullable=True, index=True
    )
    previous_due: Mapped[date | None] = mapped_column(Date, nullable=True)
    new_due: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
