import { api } from "./api";

const DEFAULT_SCENARIO_QUERY = "REALIZADO";

const qc = (competencia: string, scenario?: string) => ({
  params: { competencia, scenario: scenario ?? DEFAULT_SCENARIO_QUERY },
});

/** Lista enxuta (API structure/labors); custo sempre derivado do colaborador. */
export interface ProjectLabor {
  id: string;
  created_at: string;
  updated_at: string;
  project_id: string;
  competencia: string;
  scenario?: string;
  employee_id: string;
  allocation_percentage: number;
  monthly_cost: number;
  cost_base_source?: string;
  cost_salary_base?: number | null;
  cost_additional_costs?: number | null;
  cost_extra_hours_50?: number | null;
  cost_extra_hours_70?: number | null;
  cost_extra_hours_100?: number | null;
  cost_pj_hours_per_month?: number | null;
  cost_pj_additional_cost?: number | null;
  cost_total_override?: number | null;
}

export interface LaborCostBreakdown {
  salary_base: number;
  periculosidade: number;
  adicional_dirigida: number;
  vr: number;
  horas_extras: number;
  encargos: number;
  additional_costs: number;
  ajuda_custo: number;
}

export interface ProjectLaborDetail {
  labor_id: string;
  employee_id: string;
  name: string;
  tipo: string;
  allocation_percentage: number;
  full_cost: number;
  allocated_cost: number;
  total_cost: number;
  breakdown: LaborCostBreakdown;
  uses_cost_total_override?: boolean;
  cost_base_source?: string;
  cost_salary_base?: number | null;
  cost_additional_costs?: number | null;
  cost_extra_hours_50?: number | null;
  cost_extra_hours_70?: number | null;
  cost_extra_hours_100?: number | null;
  cost_pj_hours_per_month?: number | null;
  cost_pj_additional_cost?: number | null;
  cost_total_override?: number | null;
}

export type LaborCostPatch = {
  cost_salary_base?: number | null;
  cost_additional_costs?: number | null;
  cost_extra_hours_50?: number | null;
  cost_extra_hours_70?: number | null;
  cost_extra_hours_100?: number | null;
  cost_pj_hours_per_month?: number | null;
  cost_pj_additional_cost?: number | null;
  cost_total_override?: number | null;
};

export interface ProjectVehicle {
  id: string;
  created_at: string;
  updated_at: string;
  project_id: string;
  competencia: string;
  scenario?: string;
  vehicle_id: string;
  plate: string;
  model: string | null;
  vehicle_type: string;
  fuel_type: string | null;
  km_per_month: number | null;
  fuel_cost_realized?: number | null;
  monthly_cost: number;
  /** Combustível para comparativo (previsto = estimado; realizado = informado). */
  display_fuel_cost?: number | null;
  fuel_cost_per_km_realized?: number | null;
  driver_employee_id: string | null;
  driver_name: string | null;
}

export interface ProjectSystemCost {
  id: string;
  created_at: string;
  updated_at: string;
  project_id: string;
  competencia: string;
  scenario?: string;
  name: string;
  value: number;
}

export interface ProjectOperationalFixed {
  id: string;
  created_at: string;
  updated_at: string;
  project_id: string;
  competencia: string;
  scenario?: string;
  name: string;
  value: number;
}

export async function listLabors(
  projectId: string,
  competencia: string,
  scenario?: string
): Promise<ProjectLabor[]> {
  const { data } = await api.get<ProjectLabor[]>(
    `/projects/${projectId}/structure/labors`,
    qc(competencia, scenario)
  );
  return data;
}

export async function fetchLaborDetails(
  projectId: string,
  competencia: string,
  scenario?: string
): Promise<ProjectLaborDetail[]> {
  const { data } = await api.get<ProjectLaborDetail[]>(
    `/projects/${projectId}/labor-details`,
    qc(competencia, scenario)
  );
  return data;
}

export async function createLabor(
  projectId: string,
  body: { competencia: string; employee_id: string; allocation_percentage?: number; scenario?: string }
): Promise<ProjectLabor> {
  const { data } = await api.post<ProjectLabor>(`/projects/${projectId}/structure/labors`, body);
  return data;
}

export interface CopyLaborsFromPreviousResult {
  copied: number;
  skipped_already_linked: number;
  skipped_allocation_cap: number;
}

export async function copyLaborsFromPrevious(
  projectId: string,
  body: { competencia: string; scenario?: string }
): Promise<CopyLaborsFromPreviousResult> {
  const { data } = await api.post<CopyLaborsFromPreviousResult>(
    `/projects/${projectId}/structure/labors/copy-from-previous`,
    body
  );
  return data;
}

export async function deleteLabor(projectId: string, laborId: string): Promise<void> {
  await api.delete(`/projects/${projectId}/structure/labors/${laborId}`);
}

export async function updateLaborCosts(
  projectId: string,
  laborId: string,
  body: LaborCostPatch
): Promise<ProjectLabor> {
  const { data } = await api.patch<ProjectLabor>(
    `/projects/${projectId}/structure/labors/${laborId}`,
    body
  );
  return data;
}

export async function listVehicles(
  projectId: string,
  competencia: string,
  scenario?: string
): Promise<ProjectVehicle[]> {
  const { data } = await api.get<ProjectVehicle[]>(
    `/projects/${projectId}/structure/vehicles`,
    qc(competencia, scenario)
  );
  return data;
}

export async function createVehicle(
  projectId: string,
  body: {
    competencia: string;
    vehicle_id: string;
    scenario?: string;
    fuel_type?: "ETHANOL" | "GASOLINE" | "DIESEL";
    km_per_month?: number;
    fuel_cost_realized?: number;
  }
): Promise<ProjectVehicle> {
  const { data } = await api.post<ProjectVehicle>(`/projects/${projectId}/structure/vehicles`, body);
  return data;
}

export async function updateVehicle(
  projectId: string,
  allocationId: string,
  body: {
    vehicle_id?: string;
    fuel_type?: "ETHANOL" | "GASOLINE" | "DIESEL";
    km_per_month?: number | null;
    fuel_cost_realized?: number | null;
  }
): Promise<ProjectVehicle> {
  const { data } = await api.patch<ProjectVehicle>(
    `/projects/${projectId}/structure/vehicles/${allocationId}`,
    body
  );
  return data;
}

export async function deleteVehicle(projectId: string, allocationId: string): Promise<void> {
  await api.delete(`/projects/${projectId}/structure/vehicles/${allocationId}`);
}

export async function listSystems(
  projectId: string,
  competencia: string,
  scenario?: string
): Promise<ProjectSystemCost[]> {
  const { data } = await api.get<ProjectSystemCost[]>(
    `/projects/${projectId}/structure/systems`,
    qc(competencia, scenario)
  );
  return data;
}

export async function createSystem(
  projectId: string,
  body: { competencia: string; name: string; value: number; scenario?: string }
): Promise<ProjectSystemCost> {
  const { data } = await api.post<ProjectSystemCost>(`/projects/${projectId}/structure/systems`, body);
  return data;
}

export async function deleteSystem(projectId: string, systemId: string): Promise<void> {
  await api.delete(`/projects/${projectId}/structure/systems/${systemId}`);
}

export async function listFixedOperational(
  projectId: string,
  competencia: string,
  scenario?: string
): Promise<ProjectOperationalFixed[]> {
  const { data } = await api.get<ProjectOperationalFixed[]>(
    `/projects/${projectId}/structure/fixed-operational`,
    qc(competencia, scenario)
  );
  return data;
}

export async function createFixedOperational(
  projectId: string,
  body: { competencia: string; name: string; value: number; scenario?: string }
): Promise<ProjectOperationalFixed> {
  const { data } = await api.post<ProjectOperationalFixed>(
    `/projects/${projectId}/structure/fixed-operational`,
    body
  );
  return data;
}

export async function deleteFixedOperational(projectId: string, fixedId: string): Promise<void> {
  await api.delete(`/projects/${projectId}/structure/fixed-operational/${fixedId}`);
}
