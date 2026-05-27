from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin


class PayablePayment(TimestampUUIDMixin, Base):
    """
    Evento de pagamento de uma obrigação (PayableSnapshot).

    A competência da obrigação permanece em `PayableSnapshot.month`;
    o fluxo de caixa usa `payment_date`.
    """

    __tablename__ = "payable_payments"

    payable_snapshot_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("payable_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    reversal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    snapshot: Mapped["PayableSnapshot"] = relationship(  # noqa: F821
        "PayableSnapshot",
        back_populates="payments",
    )
