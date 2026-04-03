from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin


class Project(TimestampUUIDMixin, Base):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    code: Mapped[str | None] = mapped_column(String(50), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)

    user_links: Mapped[list["ProjectUser"]] = relationship(back_populates="project", cascade="all, delete-orphan")

    revenues: Mapped[list["Revenue"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    receivable_invoices: Mapped[list["ReceivableInvoice"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )

    employees_allocations: Mapped[list["EmployeeAllocation"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    vehicle_usages: Mapped[list["VehicleUsage"]] = relationship(back_populates="project", cascade="all, delete-orphan")

    fixed_costs: Mapped[list["ProjectFixedCost"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    cost_allocations: Mapped[list["CostAllocation"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    project_costs: Mapped[list["ProjectCost"]] = relationship(back_populates="project", cascade="all, delete-orphan")

    project_labors: Mapped[list["ProjectLabor"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    project_vehicles: Mapped[list["ProjectVehicle"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    project_system_costs: Mapped[list["ProjectSystemCost"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    project_operational_fixed: Mapped[list["ProjectOperationalFixed"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )

    results: Mapped[list["ProjectResult"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    kpis: Mapped[list["KPI"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="project", cascade="all, delete-orphan")


from app.models.costs import CostAllocation, ProjectCost, ProjectFixedCost  # noqa: E402
from app.models.project_operational import (  # noqa: E402
    ProjectLabor,
    ProjectOperationalFixed,
    ProjectSystemCost,
    ProjectVehicle,
)
from app.models.dashboard import KPI, ProjectResult  # noqa: E402
from app.models.employee import EmployeeAllocation  # noqa: E402
from app.models.financial import Invoice, Revenue  # noqa: E402
from app.models.receivable import ReceivableInvoice  # noqa: E402
from app.models.fleet import VehicleUsage  # noqa: E402
from app.models.user import ProjectUser  # noqa: E402
from app.models.alert import Alert  # noqa: E402

