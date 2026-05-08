import { api } from "./api";

export interface FinancialDashboardSummary {
  month: string; // YYYY-MM-01
  period_start: string; // YYYY-MM-01
  period_end: string; // YYYY-MM-01
  faturamento: number;
  pago: number;
  caixa: number;
}

export interface FinancialDashboardTimeseriesPoint {
  month: string; // YYYY-MM-01
  faturamento: number;
  pago: number;
  caixa: number;
}

export type FinancialDashboardBreakdownType = "faturamento" | "custos" | "caixa";

export interface FinancialDashboardGroupedItem {
  label: string;
  value: number;
}

export interface FinancialDashboardBreakdown {
  type: FinancialDashboardBreakdownType;
  month: string;
  total: number;
  groups: FinancialDashboardGroupedItem[];
  received_total?: number | null;
  received_groups?: FinancialDashboardGroupedItem[] | null;
  paid_total?: number | null;
  paid_groups?: FinancialDashboardGroupedItem[] | null;
}

export interface FinancialDashboardRead {
  summary: FinancialDashboardSummary;
  timeseries: FinancialDashboardTimeseriesPoint[];
}

export async function fetchFinancialDashboard(params: { month: string; months: number }): Promise<FinancialDashboardRead> {
  const { data } = await api.get<FinancialDashboardRead>("/financial/dashboard", { params });
  return data;
}

export async function fetchFinancialDashboardBreakdown(params: {
  type: FinancialDashboardBreakdownType;
  month: string;
}): Promise<FinancialDashboardBreakdown> {
  const { data } = await api.get<FinancialDashboardBreakdown>("/financial/dashboard/breakdown", { params });
  return data;
}

