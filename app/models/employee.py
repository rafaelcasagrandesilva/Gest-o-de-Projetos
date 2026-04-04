from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.scenario import SCENARIO_KIND_DB, Scenario
from app.database.base import Base, TimestampUUIDMixin


class Employee(TimestampUUIDMixin, Base):
    __tablename__ = "employees"

    full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    role_title: Mapped[str | None] = mapped_column(String(255))
    employment_type: Mapped[str] = mapped_column(String(10), default="CLT", nullable=False)
    salary_base: Mapped[float | None] = mapped_column(Numeric(14, 2))
    additional_costs: Mapped[float | None] = mapped_column(Numeric(14, 2))
    total_cost: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # CLT: total_cost é snapshot ao salvar (mês de referência); listagens/API recalculam por competência.
    has_periculosidade: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_adicional_dirigida: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    extra_hours_50: Mapped[float] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    extra_hours_70: Mapped[float] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    extra_hours_100: Mapped[float] = mapped_column(Numeric(10, 2), default=0, nullable=False)

    # PJ — se preenchido (>0), salário base = valor hora × pj_hours_per_month; senão = mensal fixo
    pj_hours_per_month: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    pj_additional_cost: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)

    allocations: Mapped[list["EmployeeAllocation"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )


class EmployeeAllocation(TimestampUUIDMixin, Base):
    __tablename__ = "employee_allocations"
    __table_args__ = (
        UniqueConstraint(
            "employee_id", "project_id", "start_date", "scenario", name="uq_employee_project_start_scenario"
        ),
    )

    employee_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"))
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    scenario: Mapped[Scenario] = mapped_column(SCENARIO_KIND_DB, nullable=False, default=Scenario.REALIZADO)
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date | None] = mapped_column(Date, index=True)
    allocation_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=100, nullable=False)
    monthly_cost: Mapped[float | None] = mapped_column(Numeric(14, 2))
    hours_allocated: Mapped[float | None] = mapped_column(Numeric(10, 2))

    employee: Mapped["Employee"] = relationship(back_populates="allocations")
    project: Mapped["Project"] = relationship(back_populates="employees_allocations")


from app.models.project import Project  # noqa: E402

