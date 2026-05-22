from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.asset import AssetAttachmentType, AssetPhysicalCondition, AssetStatus
from app.services.asset_categories import normalize_macro_category, normalize_tags


class ExpirationAlertLevel(str, Enum):
    NORMAL = "NORMAL"
    YELLOW = "YELLOW"
    ORANGE = "ORANGE"
    TOMORROW = "TOMORROW"
    RED = "RED"


class AssetBaseFields(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=64)
    subcategory: str | None = Field(default=None, max_length=64, description="Legado — não usar em novos cadastros")
    tags: list[str] | None = None
    size: str | None = Field(default=None, max_length=32)
    description: str | None = None

    @field_validator("category", mode="before")
    @classmethod
    def _category(cls, v: object) -> str:
        return normalize_macro_category(str(v or ""))

    @field_validator("tags", mode="before")
    @classmethod
    def _tags(cls, v: object) -> list[str] | None:
        tags = normalize_tags(v if isinstance(v, (list, str)) or v is None else str(v))
        if tags and len(tags) > 32:
            raise ValueError("Máximo de 32 tags.")
        return tags
    brand: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    serial_number: str | None = Field(default=None, max_length=120)
    patrimony_tag: str | None = Field(default=None, max_length=64)
    imei: str | None = Field(default=None, max_length=32)
    ca_number: str | None = Field(default=None, max_length=64)
    status: AssetStatus = AssetStatus.AVAILABLE
    physical_condition: AssetPhysicalCondition | None = None
    acquisition_date: date | None = None
    purchase_value: float | None = Field(default=None, ge=0)
    notes: str | None = None
    cost_center_ref: str | None = Field(default=None, description="ADMINISTRATIVO | FINANCEIRO | RH | project UUID")


class AssetCreate(AssetBaseFields):
    pass


class AssetUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=64)
    subcategory: str | None = None
    tags: list[str] | None = None
    size: str | None = Field(default=None, max_length=32)
    description: str | None = None
    brand: str | None = None

    @field_validator("category", mode="before")
    @classmethod
    def _category(cls, v: object) -> str | None:
        if v is None:
            return None
        return normalize_macro_category(str(v))

    @field_validator("tags", mode="before")
    @classmethod
    def _tags(cls, v: object) -> list[str] | None:
        if v is None:
            return None
        tags = normalize_tags(v if isinstance(v, (list, str)) else str(v))
        if tags and len(tags) > 32:
            raise ValueError("Máximo de 32 tags.")
        return tags
    model: str | None = None
    serial_number: str | None = None
    patrimony_tag: str | None = None
    imei: str | None = None
    ca_number: str | None = None
    status: AssetStatus | None = None
    physical_condition: AssetPhysicalCondition | None = None
    acquisition_date: date | None = None
    purchase_value: float | None = Field(default=None, ge=0)
    notes: str | None = None
    cost_center_ref: str | None = None


class AssetListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    asset_code: str
    name: str
    category: str
    subcategory: str | None
    size: str | None = None
    status: AssetStatus
    physical_condition: AssetPhysicalCondition | None
    purchase_value: float | None
    cost_center_label: str | None
    cost_center_ref: str | None
    current_holder_id: UUID | None
    current_holder_name: str | None
    has_inspection_control: bool = False
    next_expiration_date: date | None = None
    expiration_alert: ExpirationAlertLevel | None = None


class AssetRead(AssetListItem):
    tags: list[str] | None = None
    description: str | None
    brand: str | None
    model: str | None
    serial_number: str | None
    patrimony_tag: str | None
    imei: str | None
    ca_number: str | None
    acquisition_date: date | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class AssetAssignmentCreate(BaseModel):
    employee_id: UUID
    delivered_by_employee_id: UUID
    delivery_date: date
    notes: str | None = None

    @field_validator("delivery_date")
    @classmethod
    def delivery_not_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("Data de entrega não pode ser futura.")
        return v


class AssetAssignmentReturn(BaseModel):
    return_date: date
    returned_to_employee_id: UUID
    returned_condition: AssetPhysicalCondition
    return_notes: str | None = None

    @field_validator("return_date")
    @classmethod
    def return_not_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("Data de devolução não pode ser futura.")
        return v


class AssetAssignmentReturnUpdate(BaseModel):
    return_date: date | None = None
    returned_to_employee_id: UUID | None = None
    returned_condition: AssetPhysicalCondition | None = None
    return_notes: str | None = None

    @field_validator("return_date")
    @classmethod
    def return_not_future(cls, v: date | None) -> date | None:
        if v is not None and v > date.today():
            raise ValueError("Data de devolução não pode ser futura.")
        return v


class AssetAssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    asset_id: UUID
    employee_id: UUID
    employee_name: str
    delivered_by_employee_id: UUID | None
    delivered_by_name: str | None
    delivery_date: date
    return_date: date | None
    returned_by_employee_id: UUID | None
    returned_by_name: str | None
    returned_to_employee_id: UUID | None
    returned_to_name: str | None
    returned_condition: AssetPhysicalCondition | None
    return_notes: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class AssetInspectionCreate(BaseModel):
    inspection_type: str = Field(min_length=1, max_length=120)
    inspection_date: date
    expiration_months: int | None = Field(default=None, ge=1, le=120)
    expiration_date: date | None = None
    responsible_company: str | None = Field(default=None, max_length=255)
    report_attachment_id: UUID | None = None
    notes: str | None = None


class AssetInspectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    asset_id: UUID
    inspection_type: str
    inspection_date: date
    expiration_months: int | None
    expiration_date: date | None
    responsible_company: str | None
    report_attachment_id: UUID | None
    notes: str | None
    expiration_alert: ExpirationAlertLevel | None = None
    created_at: datetime
    updated_at: datetime


class AssetAttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    asset_id: UUID
    file_name: str
    file_type: AssetAttachmentType
    mime_type: str | None
    created_at: datetime
    download_url: str | None = None


class AssetTimelineEvent(BaseModel):
    kind: str
    at: datetime
    title: str
    detail: str | None = None


class AssetDetail(AssetRead):
    assignments: list[AssetAssignmentRead]
    inspections: list[AssetInspectionRead]
    attachments: list[AssetAttachmentRead]
    timeline: list[AssetTimelineEvent]
