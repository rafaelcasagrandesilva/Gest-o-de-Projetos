from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin

DUE_DAYS_CHOICES = frozenset({30, 60, 90})


class ReceivableInvoice(TimestampUUIDMixin, Base):
    """Nota fiscal / conta a receber — fluxo financeiro simplificado (sem pagamento parcial)."""

    __tablename__ = "receivable_invoices"

    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True)

    nf_number: Mapped[str] = mapped_column(String(64), nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    due_days: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    gross_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    net_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    client_name: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text)

    is_anticipated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    institution: Mapped[str | None] = mapped_column(String(255))

    received_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    invoice_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="EMITIDA")
    pdf_path: Mapped[str | None] = mapped_column(String(512))
    activity_log: Mapped[str | None] = mapped_column(Text)

    project: Mapped["Project"] = relationship(back_populates="receivable_invoices")
