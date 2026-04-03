from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin


class CompanyFinancialItem(TimestampUUIDMixin, Base):
    """Item corporativo: endividamento (finito) ou custo fixo recorrente."""

    __tablename__ = "company_financial_items"

    tipo: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    valor_referencia: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    payments: Mapped[list["CompanyFinancialPayment"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
    )


class CompanyFinancialPayment(TimestampUUIDMixin, Base):
    __tablename__ = "company_financial_payments"
    __table_args__ = (UniqueConstraint("item_id", "competencia", name="uq_company_financial_payment_month"),)

    item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("company_financial_items.id", ondelete="CASCADE"), index=True
    )
    competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    valor: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    item: Mapped["CompanyFinancialItem"] = relationship(back_populates="payments")
