import { isAxiosError } from "axios";
import { api } from "./api";

export interface Employee {
  id: string;
  created_at: string;
  updated_at: string;
  full_name: string;
  email: string | null;
  role_title: string | null;
  employment_type: string;
  pix_key_type?: "CPF" | "CNPJ" | "EMAIL" | "TELEFONE" | "ALEATORIA" | null;
  pix_key?: string | null;
  salary_base: number | null;
  additional_costs: number | null;
  total_cost: number;
  is_active: boolean;
  /** Ciclo de vida: admissão (start_date) / desligamento (end_date). */
  start_date: string | null;
  end_date: string | null;
  /** Centro de Custo principal + flag de alocação compartilhada. */
  cost_center: string | null;
  /** Todos os centros onde atua: o do cadastro + os das alocações ATIVAS. */
  cost_centers: string[];
  can_allocate_other_cost_centers: boolean;
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
  pix_key_type?: "CPF" | "CNPJ" | "EMAIL" | "TELEFONE" | "ALEATORIA" | null;
  pix_key?: string | null;
  salary_base?: number | null;
  additional_costs?: number | null;
  is_active?: boolean;
  /** Ciclo de vida — admissão obrigatória em novos cadastros; desligamento opcional. */
  start_date: string;
  end_date?: string | null;
  /** Centro de Custo — obrigatório no cadastro. */
  cost_center: string;
  can_allocate_other_cost_centers?: boolean;
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
  search?: string;
  offset?: number;
  limit?: number;
  /** Filtra por Centro de Custo do projeto (Mão de Obra). */
  project_id?: string;
  /** Filtra direto por Centro de Custo (precede project_id). */
  cost_center?: string;
  /** Só quem é do centro ou tem alocação ativa nele (exclui compartilhados/sem centro). */
  strict_cost_center?: boolean;
}): Promise<Employee[]> {
  const { data } = await api.get<Employee[]>("/employees/", { params });
  return data;
}

// Centros de Custo: fonte única centralizada em `./costCenters`. Re-exportado aqui por
// compatibilidade com imports existentes (`import { fetchCostCenters } from "@/services/employees"`).
export { fetchCostCenters, costCenterOptionLabel } from "./costCenters";

export type CollaboratorSearchItem = { id: string; name: string };

export async function searchCollaborators(params: { q: string; limit?: number }): Promise<CollaboratorSearchItem[]> {
  const { data } = await api.get<CollaboratorSearchItem[]>("/collaborators/search", {
    params: { q: params.q, limit: params.limit ?? 20 },
  });
  return data;
}

export async function createEmployee(payload: EmployeeCreate): Promise<Employee> {
  const { data } = await api.post<Employee>("/employees/", payload);
  return data;
}

export async function updateEmployee(
  id: string,
  payload: Partial<EmployeeCreate> & {
    /** Competência a partir da qual o novo Centro de Custo vale (histórico). Ausente = atual. */
    cost_center_effective_date?: string | null;
  },
): Promise<Employee> {
  const { data } = await api.patch<Employee>(`/employees/${id}/`, payload);
  return data;
}

export async function deleteEmployee(id: string): Promise<void> {
  await api.delete(`/employees/${id}/`);
}

export interface EmployeeMonthlyPayrollOverride {
  id: string;
  employee_id: string;
  competence_month: string;
  net_salary_amount: number | null;
  vr_amount: number | null;
  vacation_advance_amount: number | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface EmployeeMonthlyPayrollUpsert {
  net_salary_amount?: number | null;
  vr_amount?: number | null;
  vacation_advance_amount?: number | null;
  notes?: string | null;
}

export async function getMonthlyPayroll(
  employeeId: string,
  competenceMonth: string,
): Promise<EmployeeMonthlyPayrollOverride | null> {
  try {
    const { data } = await api.get<EmployeeMonthlyPayrollOverride>(
      `/employees/${employeeId}/monthly-payroll/${competenceMonth}`,
    );
    return data;
  } catch (e: unknown) {
    if (isAxiosError(e) && e.response?.status === 404) return null;
    throw e;
  }
}

export async function saveMonthlyPayroll(
  employeeId: string,
  competenceMonth: string,
  payload: EmployeeMonthlyPayrollUpsert,
): Promise<EmployeeMonthlyPayrollOverride> {
  const { data } = await api.put<EmployeeMonthlyPayrollOverride>(
    `/employees/${employeeId}/monthly-payroll/${competenceMonth}`,
    payload,
  );
  return data;
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
  const { data } = await api.get<PayrollResponse>("/employees/payroll/", {
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
  const { data } = await api.get<CompanyStaffCost[]>("/employees/staff-costs/", {
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
  const { data } = await api.post<CompanyStaffCost>("/employees/staff-costs/", body);
  return data;
}

export async function updateStaffCost(id: string, valor: number): Promise<CompanyStaffCost> {
  const { data } = await api.patch<CompanyStaffCost>(`/employees/staff-costs/${id}/`, { valor });
  return data;
}

export async function deleteStaffCost(id: string): Promise<void> {
  await api.delete(`/employees/staff-costs/${id}/`);
}

export async function previewCltCost(payload: CLTCostPreviewPayload): Promise<CLTCostPreviewResponse> {
  const { data } = await api.post<CLTCostPreviewResponse>("/employees/preview-clt-cost/", payload);
  return data;
}

export function parseCompetenciaYm(iso: string): { year: number; month: number } {
  const part = iso.slice(0, 10);
  const [ys, ms] = part.split("-");
  return { year: Number(ys), month: Number(ms) };
}

// ---------------------------------------------------------------------------
// Alocações contratuais — 1 colaborador → N contratos com remuneração própria
// ---------------------------------------------------------------------------

/**
 * INDEPENDENTE: contratos distintos, cada um com o SEU valor (sem percentual — é sempre 100%).
 * RATEIO: um único custo do colaborador dividido entre projetos por percentual (modelo histórico).
 */
export type AllocationType = "INDEPENDENTE" | "RATEIO";
/**
 * ATIVA     → vínculo vigente.
 * ENCERRADA → existiu e terminou normalmente (tem rastro financeiro).
 * CANCELADA → criado por engano, sem efeito financeiro. Some da tela por padrão.
 */
export type AssignmentStatus = "ATIVA" | "ENCERRADA" | "CANCELADA";

export type EmployeeAssignment = {
  id: string;
  employee_id: string;
  project_id: string | null;
  project_name: string | null;
  cost_center: string | null;
  allocation_type: AllocationType;
  role_title: string | null;
  /** null = omitido por Dados sensíveis (employees.sensitive), nunca zero. */
  salary_base: number | null;
  allowance: number | null;
  hours_per_month: number | null;
  employment_type: string | null;
  allocation_percent: number;
  start_date: string | null;
  end_date: string | null;
  status: AssignmentStatus;
  notes: string | null;
  is_backfilled: boolean;
  cancelled_at: string | null;
};

export type EmployeeAssignmentInput = {
  project_id?: string | null;
  cost_center?: string | null;
  allocation_type?: AllocationType;
  role_title?: string | null;
  salary_base?: number | null;
  allowance?: number | null;
  hours_per_month?: number | null;
  allocation_percent?: number | null;
  start_date?: string | null;
  end_date?: string | null;
  notes?: string | null;
};

export async function listEmployeeAssignments(
  employeeId: string,
  includeCancelled = false,
): Promise<EmployeeAssignment[]> {
  const q = includeCancelled ? "?include_cancelled=true" : "";
  const { data } = await api.get<EmployeeAssignment[]>(`/employees/${employeeId}/assignments${q}`);
  return data;
}

export async function createEmployeeAssignment(
  employeeId: string,
  payload: EmployeeAssignmentInput,
): Promise<EmployeeAssignment> {
  const { data } = await api.post<EmployeeAssignment>(`/employees/${employeeId}/assignments`, payload);
  return data;
}

export async function updateEmployeeAssignment(
  employeeId: string,
  assignmentId: string,
  payload: EmployeeAssignmentInput,
): Promise<EmployeeAssignment> {
  const { data } = await api.patch<EmployeeAssignment>(
    `/employees/${employeeId}/assignments/${assignmentId}`,
    payload,
  );
  return data;
}

/** Encerrar NUNCA exclui — o histórico de atuação precisa ser reconstruível. */
export async function closeEmployeeAssignment(
  employeeId: string,
  assignmentId: string,
  endDate?: string | null,
): Promise<EmployeeAssignment> {
  const { data } = await api.post<EmployeeAssignment>(
    `/employees/${employeeId}/assignments/${assignmentId}/close`,
    { end_date: endDate ?? null },
  );
  return data;
}

/**
 * Cancelar = criada por ENGANO. O backend recusa (409) se já houver qualquer efeito financeiro,
 * orientando a usar Encerrar — a mensagem do erro é exibida como está.
 */
export async function cancelEmployeeAssignment(
  employeeId: string,
  assignmentId: string,
  reason: string,
): Promise<EmployeeAssignment> {
  const { data } = await api.post<EmployeeAssignment>(
    `/employees/${employeeId}/assignments/${assignmentId}/cancel`,
    { reason },
  );
  return data;
}

export async function reopenEmployeeAssignment(
  employeeId: string,
  assignmentId: string,
): Promise<EmployeeAssignment> {
  const { data } = await api.post<EmployeeAssignment>(
    `/employees/${employeeId}/assignments/${assignmentId}/reopen`,
  );
  return data;
}
