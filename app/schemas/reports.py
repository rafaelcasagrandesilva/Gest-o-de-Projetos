from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ReportType = Literal[
    "project_summary",
    "company_summary",
    "employees",
    "vehicles",
    "invoices",
    "debt",
    "fixed_costs",
    "dashboard",
    "users",
    "revenues",
    "payables_detailed",
    "receivables_detailed",
    "invoices_detailed",
    "assets_inventory",
    "assets_in_use",
    "assets_inspections",
    "assets_movements",
]


class ReportGenerateRequest(BaseModel):
    type: ReportType
    filters: dict[str, Any] = Field(default_factory=dict)
    format: Literal["xlsx", "pdf"]
    scenario: str | None = Field(
        default=None,
        description="PREVISTO ou REALIZADO. Se omitido, usa filters.scenario; se ambos omitidos → REALIZADO.",
    )
