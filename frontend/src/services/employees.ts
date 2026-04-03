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

export async function previewCltCost(payload: CLTCostPreviewPayload): Promise<CLTCostPreviewResponse> {
  const { data } = await api.post<CLTCostPreviewResponse>("/employees/preview-clt-cost", payload);
  return data;
}

export function parseCompetenciaYm(iso: string): { year: number; month: number } {
  const part = iso.slice(0, 10);
  const [ys, ms] = part.split("-");
  return { year: Number(ys), month: Number(ms) };
}
