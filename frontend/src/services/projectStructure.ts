import { api } from "./api";

const q = (competencia: string) => ({ params: { competencia } });

/** Lista enxuta (API structure/labors); custo sempre derivado do colaborador. */
export interface ProjectLabor {
  id: string;
  created_at: string;
  updated_at: string;
  project_id: string;
  competencia: string;
  employee_id: string;
  allocation_percentage: number;
  monthly_cost: number;
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
}

export interface ProjectVehicle {
  id: string;
  created_at: string;
  updated_at: string;
  project_id: string;
  competencia: string;
  vehicle_id: string;
  plate: string;
  model: string | null;
  vehicle_type: string;
  fuel_type: string;
  km_per_month: number;
  monthly_cost: number;
  driver_employee_id: string | null;
  driver_name: string | null;
}

export interface ProjectSystemCost {
  id: string;
  created_at: string;
  updated_at: string;
  project_id: string;
  competencia: string;
  name: string;
  value: number;
}

export interface ProjectOperationalFixed {
  id: string;
  created_at: string;
  updated_at: string;
  project_id: string;
  competencia: string;
  name: string;
  value: number;
}

export async function listLabors(projectId: string, competencia: string): Promise<ProjectLabor[]> {
  const { data } = await api.get<ProjectLabor[]>(`/projects/${projectId}/structure/labors`, q(competencia));
  return data;
}

export async function fetchLaborDetails(
  projectId: string,
  competencia: string
): Promise<ProjectLaborDetail[]> {
  const { data } = await api.get<ProjectLaborDetail[]>(`/projects/${projectId}/labor-details`, q(competencia));
  return data;
}

export async function createLabor(
  projectId: string,
  body: { competencia: string; employee_id: string; allocation_percentage?: number }
): Promise<ProjectLabor> {
  const { data } = await api.post<ProjectLabor>(`/projects/${projectId}/structure/labors`, body);
  return data;
}

export async function deleteLabor(projectId: string, laborId: string): Promise<void> {
  await api.delete(`/projects/${projectId}/structure/labors/${laborId}`);
}

export async function listVehicles(projectId: string, competencia: string): Promise<ProjectVehicle[]> {
  const { data } = await api.get<ProjectVehicle[]>(`/projects/${projectId}/structure/vehicles`, q(competencia));
  return data;
}

export async function createVehicle(
  projectId: string,
  body: {
    competencia: string;
    vehicle_id: string;
    fuel_type: "ETHANOL" | "GASOLINE" | "DIESEL";
    km_per_month: number;
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
    km_per_month?: number;
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

export async function listSystems(projectId: string, competencia: string): Promise<ProjectSystemCost[]> {
  const { data } = await api.get<ProjectSystemCost[]>(`/projects/${projectId}/structure/systems`, q(competencia));
  return data;
}

export async function createSystem(
  projectId: string,
  body: { competencia: string; name: string; value: number }
): Promise<ProjectSystemCost> {
  const { data } = await api.post<ProjectSystemCost>(`/projects/${projectId}/structure/systems`, body);
  return data;
}

export async function deleteSystem(projectId: string, systemId: string): Promise<void> {
  await api.delete(`/projects/${projectId}/structure/systems/${systemId}`);
}

export async function listFixedOperational(
  projectId: string,
  competencia: string
): Promise<ProjectOperationalFixed[]> {
  const { data } = await api.get<ProjectOperationalFixed[]>(
    `/projects/${projectId}/structure/fixed-operational`,
    q(competencia)
  );
  return data;
}

export async function createFixedOperational(
  projectId: string,
  body: { competencia: string; name: string; value: number }
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
