from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin


class ProjectLabor(TimestampUUIDMixin, Base):
    """Vínculo projeto × colaborador × competência; custo sempre derivado do cadastro do Employee."""

    __tablename__ = "project_labors"
    __table_args__ = (UniqueConstraint("project_id", "employee_id", "competencia", name="uq_project_labors_project_employee_competencia"),)

    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    employee_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    allocation_percentage: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=100.0)

    project: Mapped["Project"] = relationship(back_populates="project_labors")
    employee: Mapped["Employee"] = relationship("Employee")


class ProjectVehicle(TimestampUUIDMixin, Base):
    """Alocação de veículo da frota ao projeto por competência (km/combustível variam por mês)."""

    __tablename__ = "project_vehicles"
    __table_args__ = (
        UniqueConstraint("project_id", "vehicle_id", "competencia", name="uq_project_vehicles_project_vehicle_competencia"),
    )

    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    vehicle_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False
    )
    fuel_type: Mapped[str] = mapped_column(String(20), nullable=False)
    km_per_month: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    monthly_cost: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    project: Mapped["Project"] = relationship(back_populates="project_vehicles")
    vehicle: Mapped["Vehicle"] = relationship("Vehicle")


class ProjectSystemCost(TimestampUUIDMixin, Base):
    __tablename__ = "project_system_costs"

    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    project: Mapped["Project"] = relationship(back_populates="project_system_costs")


class ProjectOperationalFixed(TimestampUUIDMixin, Base):
    """Custos fixos operacionais do projeto (distinto de project_fixed_costs legado por competência)."""

    __tablename__ = "project_operational_fixed"

    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    project: Mapped["Project"] = relationship(back_populates="project_operational_fixed")
