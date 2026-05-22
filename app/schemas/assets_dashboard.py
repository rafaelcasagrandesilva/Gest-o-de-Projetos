from __future__ import annotations

from pydantic import BaseModel


class AssetDashboardCountValue(BaseModel):
    count: int = 0
    value: float = 0.0


class AssetDashboardStatusKpis(BaseModel):
    total: AssetDashboardCountValue
    in_use: AssetDashboardCountValue
    available: AssetDashboardCountValue
    maintenance: AssetDashboardCountValue
    lost_or_discarded: AssetDashboardCountValue


class AssetDashboardPhysicalRow(BaseModel):
    condition: str
    label: str
    count: int = 0
    value: float = 0.0


class AssetDashboardGroupRow(BaseModel):
    key: str
    label: str
    count: int = 0
    value: float = 0.0


class AssetDashboardCostCenterRow(BaseModel):
    key: str
    label: str
    asset_count: int = 0
    amount_total: float = 0.0
    average_value: float = 0.0


class AssetDashboardAlertSummary(BaseModel):
    count: int = 0
    amount_total: float = 0.0
    damaged_count: int | None = None


class AssetDashboardAlerts(BaseModel):
    expired_inspections: AssetDashboardAlertSummary
    expiring_inspections: AssetDashboardAlertSummary
    without_holder: AssetDashboardAlertSummary
    fair_condition: AssetDashboardAlertSummary


class AssetDashboardRead(BaseModel):
    status: AssetDashboardStatusKpis
    physical_condition: list[AssetDashboardPhysicalRow]
    by_category: list[AssetDashboardGroupRow]
    by_cost_center: list[AssetDashboardCostCenterRow]
    alerts: AssetDashboardAlerts
