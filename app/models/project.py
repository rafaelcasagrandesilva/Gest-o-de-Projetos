from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin


class Project(TimestampUUIDMixin, Base):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    code: Mapped[str | None] = mapped_column(String(50), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    cost_center: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Dados contratuais (cadastrais; não participam de nenhuma regra financeira/dashboard).
    contract_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contract_value: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    contract_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Prazo total do contrato em MESES. A data final é derivada (início + prazo) e não é
    # armazenada — calculada dinamicamente no schema de leitura.
    contract_duration: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Comprador
    buyer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    buyer_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    buyer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Gestor do contrato
    manager_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    manager_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    manager_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true", index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    user_links: Mapped[list["ProjectUser"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    additives: Mapped[list["ProjectContractAdditive"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectContractAdditive.created_at.asc()",
    )
    documents: Mapped[list["ProjectDocument"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectDocument.uploaded_at.desc()",
    )

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
from app.models.project_contract import ProjectContractAdditive  # noqa: E402,F401
from app.models.project_document import ProjectDocument  # noqa: E402,F401

