from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin


class ProjectResult(TimestampUUIDMixin, Base):
    __tablename__ = "project_results"
    __table_args__ = (UniqueConstraint("project_id", "competencia", name="uq_project_result_comp"),)

    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    revenue_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    cost_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    profit: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    margin: Mapped[float] = mapped_column(Numeric(7, 4), nullable=False, default=0)

    project: Mapped["Project"] = relationship(back_populates="results")


class KPI(TimestampUUIDMixin, Base):
    __tablename__ = "kpis"
    __table_args__ = (UniqueConstraint("project_id", "competencia", "name", name="uq_kpi_proj_comp_name"),)

    project_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    value: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)

    project: Mapped["Project"] = relationship(back_populates="kpis")


from app.models.project import Project  # noqa: E402

