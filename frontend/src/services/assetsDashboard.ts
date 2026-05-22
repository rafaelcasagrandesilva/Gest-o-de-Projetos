import { api } from "@/services/api";

export type AssetDashboardCountValue = {
  count: number;
  value: number;
};

export type AssetDashboardStatusKpis = {
  total: AssetDashboardCountValue;
  in_use: AssetDashboardCountValue;
  available: AssetDashboardCountValue;
  maintenance: AssetDashboardCountValue;
  lost_or_discarded: AssetDashboardCountValue;
};

export type AssetDashboardPhysicalRow = {
  condition: string;
  label: string;
  count: number;
  value: number;
};

export type AssetDashboardGroupRow = {
  key: string;
  label: string;
  count: number;
  value: number;
};

export type AssetDashboardCostCenterRow = {
  key: string;
  label: string;
  asset_count: number;
  amount_total: number;
  average_value: number;
};

export type AssetDashboardAlertSummary = {
  count: number;
  amount_total: number;
  damaged_count: number | null;
};

export type AssetDashboardAlerts = {
  expired_inspections: AssetDashboardAlertSummary;
  expiring_inspections: AssetDashboardAlertSummary;
  without_holder: AssetDashboardAlertSummary;
  fair_condition: AssetDashboardAlertSummary;
};

export type AssetDashboardRead = {
  status: AssetDashboardStatusKpis;
  physical_condition: AssetDashboardPhysicalRow[];
  by_category: AssetDashboardGroupRow[];
  by_cost_center: AssetDashboardCostCenterRow[];
  alerts: AssetDashboardAlerts;
};

export async function fetchAssetsDashboard(): Promise<AssetDashboardRead> {
  const { data } = await api.get<AssetDashboardRead>("/assets/dashboard");
  return data;
}
