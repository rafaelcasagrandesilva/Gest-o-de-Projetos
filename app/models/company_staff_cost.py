from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.scenario import SCENARIO_KIND_DB, Scenario
from app.database.base import Base, TimestampUUIDMixin


class CompanyStaffCost(TimestampUUIDMixin, Base):
    """Custo administrativo / fora de projeto por colaborador × competência × cenário."""

    __tablename__ = "company_staff_costs"
    __table_args__ = (
        UniqueConstraint(
            "employee_id",
            "competencia",
            "scenario",
            name="uq_company_staff_costs_emp_comp_sc",
        ),
    )

    employee_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    scenario: Mapped[Scenario] = mapped_column(
        SCENARIO_KIND_DB, nullable=False, default=Scenario.REALIZADO, index=True
    )
    valor: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)

    employee: Mapped["Employee"] = relationship("Employee")


from app.models.employee import Employee  # noqa: E402
