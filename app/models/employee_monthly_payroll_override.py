from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin


class EmployeeMonthlyPayrollOverride(TimestampUUIDMixin, Base):
    """Valores reais de folha (holerite) por colaborador × mês; usado só em Contas a Pagar CLT."""

    __tablename__ = "employee_monthly_payroll_overrides"
    __table_args__ = (
        UniqueConstraint(
            "employee_id",
            "competence_month",
            name="uq_employee_monthly_payroll_emp_comp",
        ),
    )

    employee_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competence_month: Mapped[str] = mapped_column(String(7), nullable=False)
    net_salary_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    vr_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    employee: Mapped["Employee"] = relationship("Employee")


from app.models.employee import Employee  # noqa: E402
