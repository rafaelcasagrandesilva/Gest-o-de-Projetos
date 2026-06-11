from __future__ import annotations

from datetime import date
from enum import Enum
from uuid import UUID

from sqlalchemy import Boolean, Date, Enum as SAEnum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin
from app.models.employee import Employee
from app.models.project import Project


class RenegotiationType(str, Enum):
    UNIQUE = "UNIQUE"
    INSTALLMENTS = "INSTALLMENTS"


class CompanyFinancialItemType(str, Enum):
    MANUAL = "MANUAL"
    COLABORADOR_MATRIZ = "COLABORADOR_MATRIZ"


class CompanyFinancialItem(TimestampUUIDMixin, Base):
    """Item corporativo: endividamento (finito) ou custo fixo recorrente."""

    __tablename__ = "company_financial_items"

    tipo: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    item_type: Mapped[CompanyFinancialItemType] = mapped_column(
        SAEnum(CompanyFinancialItemType, name="company_financial_item_type"),
        nullable=False,
        default=CompanyFinancialItemType.MANUAL,
        server_default=CompanyFinancialItemType.MANUAL.value,
    )
    employee_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True
    )
    percentual: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    valor_referencia: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cost_center: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cost_center_project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cost_center_system: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    recurrence: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Controle operacional (custos fixos): sinaliza itens obrigatórios mensais
    # para detectar competências sem valor lançado. NÃO afeta cálculos/lançamentos.
    is_monthly_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # Campos adicionais (endividamento)
    has_legal_process: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    has_renegotiation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    renegotiated_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    renegotiation_type: Mapped[RenegotiationType | None] = mapped_column(
        SAEnum(RenegotiationType, name="renegotiation_type"),
        nullable=True,
    )
    installment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    installment_value: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    payments: Mapped[list["CompanyFinancialPayment"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
    )

    employee: Mapped[Employee | None] = relationship()
    cost_center_project: Mapped[Project | None] = relationship()


class CompanyFinancialPayment(TimestampUUIDMixin, Base):
    __tablename__ = "company_financial_payments"
    __table_args__ = (UniqueConstraint("item_id", "competencia", name="uq_company_financial_payment_month"),)

    item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("company_financial_items.id", ondelete="CASCADE"), index=True
    )
    competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    valor: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    item: Mapped["CompanyFinancialItem"] = relationship(back_populates="payments")
