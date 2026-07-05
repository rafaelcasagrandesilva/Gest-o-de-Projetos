from __future__ import annotations

import enum
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin


class ReceivableAdvanceBatchStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"


BATCH_STATUS_DB = Enum(ReceivableAdvanceBatchStatus, name="receivable_advance_batch_status")


class ReceivableAdvanceBatch(TimestampUUIDMixin, Base):
    """Operação de antecipação de NFs (ex.: borderô, factoring, FIDC)."""

    __tablename__ = "receivable_advance_batches"

    # Identificador operacional interno do SGC: sequência global simples (1, 2, 3, …),
    # única e imutável. É a identificação oficial usada internamente (Antecipações,
    # CAR, CAP, Dashboard, Logs). Independente do batch_number técnico (BT-...).
    sgc_number: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    batch_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    operation_type: Mapped[str] = mapped_column(String(32), nullable=False, default="BORDERO", index=True)
    # Código fornecido pela instituição financeira (opcional). "Número / Identificação
    # da instituição" na UI — pode ser vazio (ex.: Daycoval normalmente não tem).
    operation_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # Cópia denormalizada do nome da instituição (compatibilidade com legado/Dashboard).
    institution: Mapped[str] = mapped_column(String(255), nullable=False)
    # FK para o cadastro de instituições (nullable: registros legados só têm o texto).
    institution_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("advance_institutions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    gross_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    # received_amount é o valor que alimenta o Dashboard (fonte única de receita):
    # = previsto até o realizado ser informado; passa a = realizado depois.
    received_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    # Previsto x realizado (genérico p/ perfis como Daycoval). Previsto nunca é sobrescrito.
    expected_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    actual_received_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    discount_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    fee_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    receive_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    repayment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Repasse não apropriado (Lepta): 7% do bruto da operação, opcional. Congelado na confirmação.
    repasse_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    repasse_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    status: Mapped[ReceivableAdvanceBatchStatus] = mapped_column(
        BATCH_STATUS_DB, nullable=False, default=ReceivableAdvanceBatchStatus.OPEN, index=True
    )
    include_in_dashboard: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_by_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    items: Mapped[list["ReceivableAdvanceBatchItem"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="ReceivableAdvanceBatchItem.created_at.asc()",
    )
    institution_ref: Mapped["AdvanceInstitution | None"] = relationship(  # noqa: F821
        foreign_keys=[institution_id],
        lazy="raise",
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
    # Base de antecipação escolhida para a NF (BRUTO|LIQUIDO|LIQUIDO_MENOS_10|MANUAL).
    # Persistida na operação — NÃO recalcular a partir da NF (que pode mudar depois).
    advance_basis: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Valor antecipado da NF, congelado na confirmação da operação.
    advanced_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    batch: Mapped[ReceivableAdvanceBatch] = relationship(back_populates="items")
    invoice: Mapped["ReceivableInvoice"] = relationship(back_populates="advance_batch_item")  # noqa: F821
