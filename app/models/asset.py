from __future__ import annotations

import enum
from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Date, DateTime, Enum as SAEnum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin

if TYPE_CHECKING:
    from app.models.employee import Employee


class AssetStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    IN_USE = "IN_USE"
    MAINTENANCE = "MAINTENANCE"
    EXPIRED = "EXPIRED"
    LOST = "LOST"
    DISCARDED = "DISCARDED"


class AssetPhysicalCondition(str, enum.Enum):
    NEW = "NEW"
    GOOD = "GOOD"
    FAIR = "FAIR"
    DAMAGED = "DAMAGED"


class AssetAttachmentType(str, enum.Enum):
    TERM = "TERM"
    REPORT = "REPORT"
    CERTIFICATE = "CERTIFICATE"
    INVOICE = "INVOICE"
    MANUAL = "MANUAL"
    PHOTO = "PHOTO"
    MAINTENANCE_ORDER = "MAINTENANCE_ORDER"
    OTHER = "OTHER"


class Asset(TimestampUUIDMixin, Base):
    __tablename__ = "assets"

    asset_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subcategory: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    size: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    patrimony_tag: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    imei: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ca_number: Mapped[str | None] = mapped_column(String(64), nullable=True)

    status: Mapped[AssetStatus] = mapped_column(
        SAEnum(AssetStatus, name="asset_status"),
        nullable=False,
        default=AssetStatus.AVAILABLE,
        server_default=AssetStatus.AVAILABLE.value,
        index=True,
    )
    physical_condition: Mapped[AssetPhysicalCondition | None] = mapped_column(
        SAEnum(AssetPhysicalCondition, name="asset_physical_condition"),
        nullable=True,
    )

    acquisition_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    purchase_value: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    cost_center: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cost_center_project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cost_center_system: Mapped[str | None] = mapped_column(String(32), nullable=True)

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    assignments: Mapped[list["AssetAssignment"]] = relationship(back_populates="asset")
    inspections: Mapped[list["AssetInspection"]] = relationship(back_populates="asset")
    attachments: Mapped[list["AssetAttachment"]] = relationship(back_populates="asset")


class AssetAssignment(TimestampUUIDMixin, Base):
    """Histórico de entrega/devolução — registros concluídos são imutáveis (sem update destrutivo)."""

    __tablename__ = "asset_assignments"

    asset_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    delivered_by_employee_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    received_by_employee_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    return_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    returned_by_employee_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    returned_to_employee_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    returned_condition: Mapped[AssetPhysicalCondition | None] = mapped_column(
        SAEnum(AssetPhysicalCondition, name="asset_physical_condition"),
        nullable=True,
    )
    return_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    asset: Mapped["Asset"] = relationship(back_populates="assignments")
    returned_to_employee: Mapped[Employee | None] = relationship(
        "Employee",
        foreign_keys=[returned_to_employee_id],
    )


class AssetInspection(TimestampUUIDMixin, Base):
    __tablename__ = "asset_inspections"

    asset_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    inspection_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    inspection_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiration_months: Mapped[int | None] = mapped_column(nullable=True)
    expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    responsible_company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    report_attachment_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("asset_attachments.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    asset: Mapped["Asset"] = relationship(back_populates="inspections")


class AssetAttachment(TimestampUUIDMixin, Base):
    __tablename__ = "asset_attachments"

    asset_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[AssetAttachmentType] = mapped_column(
        SAEnum(AssetAttachmentType, name="asset_attachment_type"),
        nullable=False,
        default=AssetAttachmentType.OTHER,
        server_default=AssetAttachmentType.OTHER.value,
    )
    stored_path: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    uploaded_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    asset: Mapped["Asset"] = relationship(back_populates="attachments")
