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
]


class ReportGenerateRequest(BaseModel):
    type: ReportType
    filters: dict[str, Any] = Field(default_factory=dict)
    format: Literal["xlsx", "pdf"]
    scenario: str | None = Field(
        default=None,
        description="PREVISTO ou REALIZADO. Se omitido, usa filters.scenario; se ambos omitidos → REALIZADO.",
    )
