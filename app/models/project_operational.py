from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.scenario import SCENARIO_KIND_DB, Scenario
from app.database.base import Base, TimestampUUIDMixin


class ProjectLabor(TimestampUUIDMixin, Base):
    """Vínculo projeto × colaborador × competência × cenário; custo derivado do Employee com overrides opcionais."""

    __tablename__ = "project_labors"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "employee_id", "competencia", "scenario", name="uq_project_labors_proj_emp_comp_scenario"
        ),
    )

    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    scenario: Mapped[Scenario] = mapped_column(
        SCENARIO_KIND_DB, nullable=False, default=Scenario.REALIZADO, index=True
    )
    employee_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    allocation_percentage: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=100.0)

    # Overrides de custo para este projeto × competência × cenário (null = usar cadastro do colaborador)
    cost_salary_base: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    cost_additional_costs: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    cost_extra_hours_50: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    cost_extra_hours_70: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    cost_extra_hours_100: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    cost_pj_hours_per_month: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    cost_pj_additional_cost: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    cost_total_override: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="project_labors")
    employee: Mapped["Employee"] = relationship("Employee")


class ProjectVehicle(TimestampUUIDMixin, Base):
    """Alocação de veículo da frota ao projeto por competência (km/combustível variam por mês)."""

    __tablename__ = "project_vehicles"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "vehicle_id", "competencia", "scenario", name="uq_project_vehicles_proj_veh_comp_scenario"
        ),
    )

    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    scenario: Mapped[Scenario] = mapped_column(
        SCENARIO_KIND_DB, nullable=False, default=Scenario.REALIZADO, index=True
    )
    vehicle_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False
    )
    fuel_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    km_per_month: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    # REALIZADO: valor informado de combustível no mês (não calculado por km).
    fuel_cost_realized: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    monthly_cost: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    project: Mapped["Project"] = relationship(back_populates="project_vehicles")
    vehicle: Mapped["Vehicle"] = relationship("Vehicle")


class ProjectSystemCost(TimestampUUIDMixin, Base):
    __tablename__ = "project_system_costs"

    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    scenario: Mapped[Scenario] = mapped_column(SCENARIO_KIND_DB, nullable=False, default=Scenario.REALIZADO)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    project: Mapped["Project"] = relationship(back_populates="project_system_costs")


class ProjectOperationalFixed(TimestampUUIDMixin, Base):
    """Custos fixos operacionais do projeto (distinto de project_fixed_costs legado por competência)."""

    __tablename__ = "project_operational_fixed"

    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    scenario: Mapped[Scenario] = mapped_column(SCENARIO_KIND_DB, nullable=False, default=Scenario.REALIZADO)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    project: Mapped["Project"] = relationship(back_populates="project_operational_fixed")
