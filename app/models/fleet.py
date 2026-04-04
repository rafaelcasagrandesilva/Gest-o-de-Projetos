from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.scenario import SCENARIO_KIND_DB, Scenario
from app.database.base import Base, TimestampUUIDMixin


class Vehicle(TimestampUUIDMixin, Base):
    __tablename__ = "vehicles"

    plate: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    model: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(255))
    vehicle_type: Mapped[str] = mapped_column(String(20), nullable=False, default="LIGHT")
    monthly_cost: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    driver_employee_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    driver: Mapped["Employee | None"] = relationship(
        "Employee", foreign_keys=[driver_employee_id], lazy="joined"
    )
    usages: Mapped[list["VehicleUsage"]] = relationship(back_populates="vehicle", cascade="all, delete-orphan")


class VehicleUsage(TimestampUUIDMixin, Base):
    __tablename__ = "vehicle_usages"
    __table_args__ = (
        UniqueConstraint(
            "vehicle_id", "project_id", "usage_date", "scenario", name="uq_vehicle_project_date_scenario"
        ),
    )

    vehicle_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"))
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    scenario: Mapped[Scenario] = mapped_column(SCENARIO_KIND_DB, nullable=False, default=Scenario.REALIZADO)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    cost_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(String(255))

    vehicle: Mapped["Vehicle"] = relationship(back_populates="usages")
    project: Mapped["Project"] = relationship(back_populates="vehicle_usages")


from app.models.employee import Employee  # noqa: E402
from app.models.project import Project  # noqa: E402

