from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

PayableImportRowStatus = Literal["valid", "duplicate", "error", "empty"]


class PayableImportColumnMapping(BaseModel):
    name: str | None = None
    cost_center: str | None = None
    due_date: str | None = None
    amount: str | None = None
    category: str | None = None
    observation: str | None = None


class PayableImportPreviewRow(BaseModel):
    line_number: int
    # Valores "como estavam na planilha", já convertidos para string (para auditoria do usuário).
    original_name: str | None = None
    original_cost_center: str | None = None
    original_due_date: str | None = None
    original_amount: str | None = None
    original_category: str | None = None
    original_observation: str | None = None

    cost_center: str | None = None
    alias_applied: bool = False
    name: str | None = None
    due_date: date | None = None
    amount: float | None = None
    observation: str | None = None
    category: str | None = None
    payment_month: date | None = None
    status: PayableImportRowStatus
    message: str | None = None


class PayableImportPreviewResult(BaseModel):
    total_rows: int = 0
    valid_count: int = 0
    duplicate_count: int = 0
    error_count: int = 0
    empty_count: int = 0
    rows: list[PayableImportPreviewRow] = Field(default_factory=list)


class PayableImportConfirmResult(BaseModel):
    imported: int = 0
    skipped_duplicate: int = 0
    skipped_empty: int = 0
    errors: int = 0
    error_details: list[str] = Field(default_factory=list, max_length=50)


class PayableImportAnalyzeResult(BaseModel):
    header_row: int
    columns: list[str]
    sample_rows: list[dict[str, Any]]
    suggested_mapping: PayableImportColumnMapping
    detected_legacy_template: bool = False
    total_data_rows: int = 0


class PayableImportTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    header_row: int = Field(1, ge=1, le=500)
    column_mapping: PayableImportColumnMapping

    @field_validator("column_mapping", mode="before")
    @classmethod
    def mapping_dict(cls, v: Any) -> PayableImportColumnMapping:
        if isinstance(v, PayableImportColumnMapping):
            return v
        if isinstance(v, dict):
            return PayableImportColumnMapping.model_validate(v)
        raise ValueError("column_mapping inválido.")


class PayableImportCostCenterScanResult(BaseModel):
    unknown_centers: list[str] = Field(default_factory=list)
    available_targets: list[str] = Field(default_factory=list)


class PayableImportTemplateRead(BaseModel):
    id: UUID
    name: str
    header_row: int
    column_mapping: PayableImportColumnMapping
    created_at: datetime
    updated_at: datetime
