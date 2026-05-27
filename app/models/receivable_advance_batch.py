from __future__ import annotations

import enum
from datetime import date
from uuid import UUID

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin


class ReceivableAdvanceBatchStatus(str, enum.Enum):
    OPEN = "OPEN"
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"


BATCH_STATUS_DB = Enum(ReceivableAdvanceBatchStatus, name="receivable_advance_batch_status")


class ReceivableAdvanceBatch(TimestampUUIDMixin, Base):
    """Operação de antecipação de NFs (ex.: borderô, factoring, FIDC)."""

    __tablename__ = "receivable_advance_batches"

    batch_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    operation_type: Mapped[str] = mapped_column(String(32), nullable=False, default="BORDERO", index=True)
    operation_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    institution: Mapped[str] = mapped_column(String(255), nullable=False)
    gross_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    received_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    discount_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    fee_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    receive_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    repayment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ReceivableAdvanceBatchStatus] = mapped_column(
        BATCH_STATUS_DB, nullable=False, default=ReceivableAdvanceBatchStatus.OPEN, index=True
    )
    created_by_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    items: Mapped[list["ReceivableAdvanceBatchItem"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="ReceivableAdvanceBatchItem.created_at.asc()",
    )
    created_by: Mapped["User | None"] = relationship()  # noqa: F821


class ReceivableAdvanceBatchItem(TimestampUUIDMixin, Base):
    __tablename__ = "receivable_advance_batch_items"
    __table_args__ = (UniqueConstraint("batch_id", "invoice_id", name="uq_advance_batch_item_invoice"),)

    batch_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("receivable_advance_batches.id", ondelete="CASCADE"), index=True
    )
    invoice_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("receivable_invoices.id", ondelete="CASCADE"), index=True
    )
    invoice_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    batch: Mapped[ReceivableAdvanceBatch] = relationship(back_populates="items")
    invoice: Mapped["ReceivableInvoice"] = relationship(back_populates="advance_batch_item")  # noqa: F821
