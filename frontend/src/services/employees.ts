import { api } from "./api";

export interface Employee {
  id: string;
  created_at: string;
  updated_at: string;
  full_name: string;
  email: string | null;
  role_title: string | null;
  employment_type: string;
  salary_base: number | null;
  additional_costs: number | null;
  total_cost: number;
  is_active: boolean;
  has_periculosidade: boolean;
  has_adicional_dirigida: boolean;
  extra_hours_50: number;
  extra_hours_70: number;
  extra_hours_100: number;
  pj_hours_per_month: number | null;
  pj_additional_cost: number;
}

export interface EmployeeCreate {
  full_name: string;
  email?: string | null;
  role_title?: string | null;
  employment_type?: "CLT" | "PJ";
  salary_base?: number | null;
  additional_costs?: number | null;
  is_active?: boolean;
  has_periculosidade?: boolean;
  has_adicional_dirigida?: boolean;
  extra_hours_50?: number;
  extra_hours_70?: number;
  extra_hours_100?: number;
  pj_hours_per_month?: number | null;
  pj_additional_cost?: number;
  /** YYYY-MM-DD (dia 1 do mês) */
  cost_reference_competencia?: string | null;
}

export interface CLTCostPreviewPayload {
  salary_base: number;
  has_periculosidade?: boolean;
  has_adicional_dirigida?: boolean;
  extra_hours_50?: number;
  extra_hours_70?: number;
  extra_hours_100?: number;
  additional_costs?: number | null;
  year: number;
  month: number;
}

export interface CLTCostPreviewResponse {
  total_cost: number;
  business_days: number;
  reference_month: string;
}

export async function listEmployees(params?: {
  competencia?: string;
  offset?: number;
  limit?: number;
}): Promise<Employee[]> {
  const { data } = await api.get<Employee[]>("/employees", { params });
  return data;
}

export async function createEmployee(payload: EmployeeCreate): Promise<Employee> {
  const { data } = await api.post<Employee>("/employees", payload);
  return data;
}

export async function updateEmployee(id: string, payload: Partial<EmployeeCreate>): Promise<Employee> {
  const { data } = await api.patch<Employee>(`/employees/${id}`, payload);
  return data;
}

export async function deleteEmployee(id: string): Promise<void> {
  await api.delete(`/employees/${id}`);
}

const DEFAULT_SCENARIO_QUERY = "REALIZADO";

export interface PayrollProjectSlice {
  project_id: string;
  project_name: string;
  labor_id: string;
  allocation_percentage: number;
  full_monthly_cost: number;
  allocated_cost: number;
}

export interface PayrollLine {
  employee_id: string;
  full_name: string;
  employment_type: string;
  role_title: string | null;
  is_active: boolean;
  by_project: PayrollProjectSlice[];
  projects_total: number;
  administrative_cost: number;
  grand_total: number;
}

export interface PayrollTotals {
  sum_projects: number;
  sum_administrative: number;
  grand_total: number;
}

export interface PayrollResponse {
  competencia: string;
  scenario: string;
  project_id: string | null;
  lines: PayrollLine[];
  totals: PayrollTotals;
}

export async function fetchPayroll(params: {
  competencia: string;
  scenario?: string;
  project_id?: string;
}): Promise<PayrollResponse> {
  const { data } = await api.get<PayrollResponse>("/employees/payroll", {
    params: {
      competencia: params.competencia,
      scenario: params.scenario ?? DEFAULT_SCENARIO_QUERY,
      ...(params.project_id ? { project_id: params.project_id } : {}),
    },
  });
  return data;
}

export interface CompanyStaffCost {
  id: string;
  created_at: string;
  updated_at: string;
  employee_id: string;
  competencia: string;
  scenario: string;
  valor: number;
  employee_full_name?: string | null;
}

export async function listStaffCosts(params: {
  competencia: string;
  scenario?: string;
}): Promise<CompanyStaffCost[]> {
  const { data } = await api.get<CompanyStaffCost[]>("/employees/staff-costs", {
    params: {
      competencia: params.competencia,
      scenario: params.scenario ?? DEFAULT_SCENARIO_QUERY,
    },
  });
  return data;
}

export async function createStaffCost(body: {
  employee_id: string;
  competencia: string;
  valor: number;
  scenario?: string;
}): Promise<CompanyStaffCost> {
  const { data } = await api.post<CompanyStaffCost>("/employees/staff-costs", body);
  return data;
}

export async function updateStaffCost(id: string, valor: number): Promise<CompanyStaffCost> {
  const { data } = await api.patch<CompanyStaffCost>(`/employees/staff-costs/${id}`, { valor });
  return data;
}

export async function deleteStaffCost(id: string): Promise<void> {
  await api.delete(`/employees/staff-costs/${id}`);
}

export async function previewCltCost(payload: CLTCostPreviewPayload): Promise<CLTCostPreviewResponse> {
  const { data } = await api.post<CLTCostPreviewResponse>("/employees/preview-clt-cost", payload);
  return data;
}

export function parseCompetenciaYm(iso: string): { year: number; month: number } {
  const part = iso.slice(0, 10);
  const [ys, ms] = part.split("-");
  return { year: Number(ys), month: Number(ms) };
}
