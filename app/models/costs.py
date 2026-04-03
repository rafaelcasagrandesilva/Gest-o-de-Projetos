from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin


class ProjectFixedCost(TimestampUUIDMixin, Base):
    __tablename__ = "project_fixed_costs"
    __table_args__ = (UniqueConstraint("project_id", "competencia", "name", name="uq_project_fixed_cost"),)

    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    amount_real: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    amount_calculated: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)

    project: Mapped["Project"] = relationship(back_populates="fixed_costs")


class CorporateCost(TimestampUUIDMixin, Base):
    __tablename__ = "corporate_costs"
    __table_args__ = (UniqueConstraint("competencia", "name", name="uq_corporate_cost"),)

    competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    amount_real: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    amount_calculated: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)

    allocations: Mapped[list["CostAllocation"]] = relationship(
        back_populates="corporate_cost", cascade="all, delete-orphan"
    )


class CostAllocation(TimestampUUIDMixin, Base):
    __tablename__ = "cost_allocations"
    __table_args__ = (UniqueConstraint("corporate_cost_id", "project_id", name="uq_corp_cost_project"),)

    corporate_cost_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("corporate_costs.id", ondelete="CASCADE")
    )
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    allocated_amount_real: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    allocated_amount_calculated: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)

    corporate_cost: Mapped["CorporateCost"] = relationship(back_populates="allocations")
    project: Mapped["Project"] = relationship(back_populates="cost_allocations")


class ProjectCost(TimestampUUIDMixin, Base):
    __tablename__ = "project_costs"

    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    cost_type: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    cost_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False)

    project: Mapped["Project"] = relationship(back_populates="project_costs")


from app.models.project import Project  # noqa: E402

