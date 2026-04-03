import { api } from "./api";

export interface DirectorSummary {
  /** Ausente ou null no consolidado global; preenchido ao filtrar por projeto */
  project_id?: string | null;
  competencia: string;
  revenue_total: number;
  total_revenue: number;
  cost_total: number;
  total_cost: number;
  total_retention: number;
  operational_profit: number;
  net_profit: number;
  margin_operational: number;
  margin_net: number;
  /** Igual a operational_profit (compat) */
  profit: number;
  /** Igual a margin_operational (compat) */
  margin: number;
  /** Receita − custos operacionais (mão de obra, veículos, sistemas, fixos operacionais) */
  ebitda?: number;
  /** Fração da receita (ex.: 0,15 = 15%) */
  ebitda_margin?: number;
  operational_cost?: number;
  labor_cost?: number;
  vehicle_cost?: number;
  system_cost?: number;
  fixed_operational_cost?: number;
  tax_amount?: number;
  overhead_amount?: number;
  anticipation_amount?: number;
  /** Percentual do custo sobre a receita (0–100), 1 decimal */
  labor_cost_pct?: number;
  vehicle_cost_pct?: number;
  system_cost_pct?: number;
  fixed_operational_cost_pct?: number;
  operational_cost_pct?: number;
  tax_amount_pct?: number;
  overhead_amount_pct?: number;
  anticipation_amount_pct?: number;
}

export interface MonthlyPoint {
  competencia: string;
  revenue_total: number;
  total_revenue: number;
  cost_total: number;
  total_cost: number;
  total_retention?: number;
  operational_profit?: number;
  net_profit?: number;
  margin_operational?: number;
  margin_net?: number;
  profit: number;
  margin: number;
  ebitda?: number;
  ebitda_margin?: number;
  operational_cost?: number;
  tax_amount?: number;
  overhead_amount?: number;
  anticipation_amount?: number;
  labor_cost_pct?: number;
  vehicle_cost_pct?: number;
  system_cost_pct?: number;
  fixed_operational_cost_pct?: number;
  operational_cost_pct?: number;
  tax_amount_pct?: number;
  overhead_amount_pct?: number;
  anticipation_amount_pct?: number;
}

export interface FinancialDashboardSummary {
  summary: DirectorSummary;
  monthly_series: MonthlyPoint[];
}

export async function fetchFinancialSummary(params: {
  competencia?: string;
  months?: number;
  /** Omitir ou vazio = consolidado global (ADMIN ou CONSULTA; GESTOR deve informar projeto) */
  project_id?: string;
}): Promise<FinancialDashboardSummary> {
  const q: Record<string, string | number> = {};
  if (params.competencia != null) q.competencia = params.competencia;
  if (params.months != null) q.months = params.months;
  if (params.project_id) q.project_id = params.project_id;
  const { data } = await api.get<FinancialDashboardSummary>("/dashboard/summary", { params: q });
  return data;
}

export interface ProjectSummary {
  project_id: string;
  competencia: string;
  revenue_total: number;
  total_revenue: number;
  cost_total: number;
  total_cost: number;
  total_retention: number;
  operational_profit: number;
  net_profit: number;
  margin_operational: number;
  margin_net: number;
  profit: number;
  margin: number;
  ebitda?: number;
  ebitda_margin?: number;
  operational_cost?: number;
  labor_cost?: number;
  vehicle_cost?: number;
  system_cost?: number;
  fixed_operational_cost?: number;
  tax_amount?: number;
  overhead_amount?: number;
  anticipation_amount?: number;
  labor_cost_pct?: number;
  vehicle_cost_pct?: number;
  system_cost_pct?: number;
  fixed_operational_cost_pct?: number;
  operational_cost_pct?: number;
  tax_amount_pct?: number;
  overhead_amount_pct?: number;
  anticipation_amount_pct?: number;
}

export interface ProjectDashboardResponse {
  summary: ProjectSummary;
  monthly_series: MonthlyPoint[];
}

export async function fetchProjectFinancialDashboard(
  projectId: string,
  params?: { competencia?: string; months?: number }
): Promise<ProjectDashboardResponse> {
  const { data } = await api.get<ProjectDashboardResponse>(`/dashboard/project/${projectId}`, { params });
  return data;
}
