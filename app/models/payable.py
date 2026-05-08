from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin


class Payable(TimestampUUIDMixin, Base):
    __tablename__ = "payables"

    description: Mapped[str] = mapped_column(String(255), nullable=False)
    supplier_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    # Competência (mês referência). Usamos day=1 como convenção.
    competence: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    chart_account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("chart_of_accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    cost_center: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )

    chart_account: Mapped["ChartOfAccounts"] = relationship()
    project: Mapped["Project"] = relationship()


from app.models.chart_of_accounts import ChartOfAccounts  # noqa: E402
from app.models.project import Project  # noqa: E402

