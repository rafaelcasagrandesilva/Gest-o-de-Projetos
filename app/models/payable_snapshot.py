from __future__ import annotations

import enum
from datetime import date
from uuid import UUID

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin


class PayableSnapshotType(str, enum.Enum):
    COLLABORATOR = "COLLABORATOR"
    VEHICLE = "VEHICLE"
    FIXED_COST = "FIXED_COST"
    ENDIVIDAMENTO = "ENDIVIDAMENTO"
    # Legacy name kept so old databases/rows can still be read until migrated.
    FINANCIAL = "FINANCIAL"
    ANTECIPACAO = "ANTECIPACAO"
    MANUAL = "MANUAL"


PAYABLE_SNAPSHOT_TYPE_DB = Enum(PayableSnapshotType, name="payable_snapshot_type")


class PayableSnapshot(TimestampUUIDMixin, Base):
    """
    Snapshot mensal de contas a pagar (imutável após geração).

    `month` é a competência do pagamento (ex.: 2026-05-01).
    Os valores são copiados do mês anterior (fonte) no momento da geração.
    """

    __tablename__ = "payable_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "month",
            "type",
            "ref_id",
            "project_id",
            "name",
            "category",
            "cost_center",
            name="uq_payable_snapshot_identity",
        ),
    )

    month: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    type: Mapped[PayableSnapshotType] = mapped_column(PAYABLE_SNAPSHOT_TYPE_DB, nullable=False, index=True)

    ref_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    cost_center: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    amount_original: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    amount_final: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    amount_paid: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)

    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    observation: Mapped[str | None] = mapped_column(Text, nullable=True)

    payments: Mapped[list["PayablePayment"]] = relationship(  # noqa: F821
        "PayablePayment",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
