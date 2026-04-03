from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin


class Revenue(TimestampUUIDMixin, Base):
    __tablename__ = "revenues"
    __table_args__ = (UniqueConstraint("project_id", "competencia", "description", name="uq_revenue_comp_desc"),)

    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="recebido", nullable=False, index=True)
    has_retention: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="revenues")


class Invoice(TimestampUUIDMixin, Base):
    __tablename__ = "invoices"

    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="open", nullable=False, index=True)
    supplier: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(255))

    project: Mapped["Project"] = relationship(back_populates="invoices")
    anticipations: Mapped[list["InvoiceAnticipation"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )


class InvoiceAnticipation(TimestampUUIDMixin, Base):
    __tablename__ = "invoice_anticipations"

    invoice_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"))
    anticipated_at: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    fee_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(255))

    invoice: Mapped["Invoice"] = relationship(back_populates="anticipations")


from app.models.project import Project  # noqa: E402

