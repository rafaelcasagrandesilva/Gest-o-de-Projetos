from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin


class EmployeeCostCenterHistory(TimestampUUIDMixin, Base):
    """Histórico temporal do Centro de Custo de um colaborador (fonte da verdade).

    Cada linha vale de `start_date` até `end_date` (NULL = vigente). O campo
    `employees.cost_center` permanece apenas como CACHE do centro vigente. Regra:
    nunca editar histórico — sempre fechar a linha anterior e abrir uma nova.
    """

    __tablename__ = "employee_cost_center_history"
    __table_args__ = (
        Index("ix_employee_cost_center_history_employee_start", "employee_id", "start_date"),
    )

    employee_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cost_center: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    employee: Mapped["Employee"] = relationship(back_populates="cost_center_history")  # noqa: F821


class VehicleCostCenterHistory(TimestampUUIDMixin, Base):
    """Histórico temporal do Centro de Custo de um veículo (mesma semântica do colaborador)."""

    __tablename__ = "vehicle_cost_center_history"
    __table_args__ = (
        Index("ix_vehicle_cost_center_history_vehicle_start", "vehicle_id", "start_date"),
    )

    vehicle_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cost_center: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    vehicle: Mapped["Vehicle"] = relationship(back_populates="cost_center_history")  # noqa: F821
