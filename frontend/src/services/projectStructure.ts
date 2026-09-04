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
  /** Redigido (null) sem `projects.sensitive`. */
  monthly_cost: number | null;
  cost_base_source?: string;
  cost_salary_base?: number | null;
  cost_extra_hours_50?: number | null;
  cost_extra_hours_70?: number | null;
  cost_extra_hours_100?: number | null;
  cost_pj_hours_per_month?: number | null;
  cost_pj_additional_cost?: number | null;
  cost_total_override?: number | null;
}

/** Todos os campos são redigidos (null) sem `projects.sensitive`. */
export interface LaborCostBreakdown {
  salary_base: number | null;
  periculosidade: number | null;
  adicional_dirigida: number | null;
  vr: number | null;
  horas_extras: number | null;
  encargos: number | null;
  additional_costs: number | null;
  ajuda_custo: number | null;
}

export interface ProjectLaborDetail {
  labor_id: string;
  employee_id: string;
  name: string;
  tipo: string;
  allocation_percentage: number;
  /** Redigidos (null) sem `projects.sensitive`. */
  full_cost: number | null;
  allocated_cost: number | null;
  /** Avulsos (Componentes Variáveis) do colaborador — valor de face, sem rateio. */
  variable_components_total: number | null;
  /** allocated_cost + variable_components_total (custo cheio no projeto). */
  total_cost: number | null;
  breakdown: LaborCostBreakdown;
  uses_cost_total_override?: boolean;
  cost_base_source?: string;
  cost_salary_base?: number | null;
  cost_extra_hours_50?: number | null;
  cost_extra_hours_70?: number | null;
  cost_extra_hours_100?: number | null;
  cost_pj_hours_per_month?: number | null;
  cost_pj_additional_cost?: number | null;
  cost_total_override?: number | null;
}

export type LaborCostPatch = {
  cost_salary_base?: number | null;
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
  /** Redigido (null) sem `projects.sensitive`. */
  monthly_cost: number | null;
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
  /** Redigido (null) sem `projects.sensitive`. */
  value: number | null;
}

export interface ProjectOperationalFixed {
  id: string;
  created_at: string;
  updated_at: string;
  project_id: string;
  competencia: string;
  scenario?: string;
  name: string;
  /** Redigido (null) sem `projects.sensitive`. */
  value: number | null;
}

export async function listLabors(
  projectId: string,
  competencia: string,
  scenario?: string
): Promise<ProjectLabor[]> {
  const { data } = await api.get<ProjectLabor[]>(
    `/projects/${projectId}/structure/labors/`,
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
    `/projects/${projectId}/labor-details/`,
    qc(competencia, scenario)
  );
  return data;
}

export async function createLabor(
  projectId: string,
  body: { competencia: string; employee_id: string; allocation_percentage?: number; scenario?: string }
): Promise<ProjectLabor> {
  const { data } = await api.post<ProjectLabor>(`/projects/${projectId}/structure/labors/`, body);
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
    `/projects/${projectId}/structure/labors/copy-from-previous/`,
    body
  );
  return data;
}

// --- Inicializar Competência (fluxo único reutilizável por todas as abas) ---

export type InitializeOrigin = "previous_realizado" | "current_previsto" | "previous_previsto";
export type CostCategory = "labor" | "vehicles" | "systems" | "misc";

export interface CategoryCopyResult {
  category: CostCategory;
  label: string;
  copied: number;
  /** Nomes do que ficou de fora da cópia. Vazio no caminho normal — a cópia é exata. */
  skipped?: string[];
}

export interface InitializeCompetenciaResult {
  source_competencia: string;
  source_scenario: string;
  target_competencia: string;
  target_scenario: string;
  results: CategoryCopyResult[];
}

export async function initializeCompetencia(
  projectId: string,
  body: {
    competencia: string;
    origin: InitializeOrigin;
    /** Cenário de DESTINO — onde a cópia é gravada. A origem só diz de onde os dados vêm. */
    target_scenario: "PREVISTO" | "REALIZADO";
    categories: CostCategory[];
  },
): Promise<InitializeCompetenciaResult> {
  const { data } = await api.post<InitializeCompetenciaResult>(
    `/projects/${projectId}/structure/initialize-competencia/`,
    body,
  );
  return data;
}

export async function deleteLabor(projectId: string, laborId: string): Promise<void> {
  await api.delete(`/projects/${projectId}/structure/labors/${laborId}/`);
}

export interface BulkDeleteResult {
  total: number;
  excluidos: number;
  /** Itens com pagamento já lançado no CAP — excluir deixa o título órfão. */
  com_pagamento: string[];
}

/**
 * Exclui vários itens de uma aba de uma vez. Com `confirm: false` o backend só RELATA o
 * que aconteceria — é assim que a tela avisa antes de destruir.
 */
export async function bulkDeleteStructureItems(
  projectId: string,
  category: CostCategory,
  ids: string[],
  confirm: boolean,
): Promise<BulkDeleteResult> {
  const { data } = await api.post<BulkDeleteResult>(
    `/projects/${projectId}/structure/bulk-delete`,
    { category, ids, confirm },
  );
  return data;
}

/** Edição de Sistemas e Custos diversos (o backend já expunha PATCH; faltava a tela). */
export async function updateSystem(
  projectId: string,
  systemId: string,
  body: { name?: string; value?: number },
): Promise<ProjectSystemCost> {
  const { data } = await api.patch<ProjectSystemCost>(
    `/projects/${projectId}/structure/systems/${systemId}`,
    body,
  );
  return data;
}

export async function updateFixedOperational(
  projectId: string,
  fixedId: string,
  body: { name?: string; value?: number },
): Promise<ProjectOperationalFixed> {
  const { data } = await api.patch<ProjectOperationalFixed>(
    `/projects/${projectId}/structure/fixed-operational/${fixedId}`,
    body,
  );
  return data;
}

export async function updateLaborCosts(
  projectId: string,
  laborId: string,
  body: LaborCostPatch
): Promise<ProjectLabor> {
  const { data } = await api.patch<ProjectLabor>(
    `/projects/${projectId}/structure/labors/${laborId}/`,
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
    `/projects/${projectId}/structure/vehicles/`,
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
  const { data } = await api.post<ProjectVehicle>(`/projects/${projectId}/structure/vehicles/`, body);
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
    `/projects/${projectId}/structure/vehicles/${allocationId}/`,
    body
  );
  return data;
}

export async function deleteVehicle(projectId: string, allocationId: string): Promise<void> {
  await api.delete(`/projects/${projectId}/structure/vehicles/${allocationId}/`);
}

export async function listSystems(
  projectId: string,
  competencia: string,
  scenario?: string
): Promise<ProjectSystemCost[]> {
  const { data } = await api.get<ProjectSystemCost[]>(
    `/projects/${projectId}/structure/systems/`,
    qc(competencia, scenario)
  );
  return data;
}

export async function createSystem(
  projectId: string,
  body: { competencia: string; name: string; value: number; scenario?: string }
): Promise<ProjectSystemCost> {
  const { data } = await api.post<ProjectSystemCost>(`/projects/${projectId}/structure/systems/`, body);
  return data;
}

export async function deleteSystem(projectId: string, systemId: string): Promise<void> {
  await api.delete(`/projects/${projectId}/structure/systems/${systemId}/`);
}

export async function listFixedOperational(
  projectId: string,
  competencia: string,
  scenario?: string
): Promise<ProjectOperationalFixed[]> {
  const { data } = await api.get<ProjectOperationalFixed[]>(
    `/projects/${projectId}/structure/fixed-operational/`,
    qc(competencia, scenario)
  );
  return data;
}

export async function createFixedOperational(
  projectId: string,
  body: { competencia: string; name: string; value: number; scenario?: string }
): Promise<ProjectOperationalFixed> {
  const { data } = await api.post<ProjectOperationalFixed>(
    `/projects/${projectId}/structure/fixed-operational/`,
    body
  );
  return data;
}

export async function deleteFixedOperational(projectId: string, fixedId: string): Promise<void> {
  await api.delete(`/projects/${projectId}/structure/fixed-operational/${fixedId}/`);
}
