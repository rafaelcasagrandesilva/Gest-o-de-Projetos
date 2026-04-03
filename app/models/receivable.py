from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin


class ReceivableInvoice(TimestampUUIDMixin, Base):
    """Nota fiscal / conta a receber (controle operacional)."""

    __tablename__ = "receivable_invoices"

    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    numero_nf: Mapped[str] = mapped_column(String(64), nullable=False)
    data_emissao: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    valor_bruto: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    vencimento: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    data_prevista_pagamento: Mapped[date | None] = mapped_column(Date, nullable=True)

    numero_pedido: Mapped[str | None] = mapped_column(String(128))
    numero_conformidade: Mapped[str | None] = mapped_column(String(128))
    observacao: Mapped[str | None] = mapped_column(Text)

    antecipada: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    instituicao: Mapped[str | None] = mapped_column(String(255))
    taxa_juros_mensal: Mapped[float | None] = mapped_column(Numeric(10, 6))

    project: Mapped["Project"] = relationship(back_populates="receivable_invoices")
    payments: Mapped[list["ReceivableInvoicePayment"]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
    )


class ReceivableInvoicePayment(TimestampUUIDMixin, Base):
    __tablename__ = "receivable_invoice_payments"

    invoice_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("receivable_invoices.id", ondelete="CASCADE"), index=True
    )
    data_recebimento: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    valor: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    invoice: Mapped["ReceivableInvoice"] = relationship(back_populates="payments")
