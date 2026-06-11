import { api } from "./api";

/** Padrão de cenário quando não informado (alinhado ao backend). */
const DEFAULT_SCENARIO_QUERY = "REALIZADO";

export interface ProjectRoi {
  project_id: string;
  project_name: string;
  competencia: string;
  scenario: string;
  revenue: number;
  cost: number;
  operational_profit: number;
  /** Fração (ex.: 0,33 = 33%). null = custo zero (ROI indefinido). */
  roi: number | null;
  roi_pct: number | null;
}

export interface RoiRanking {
  competencia: string;
  scenario: string;
  only_active: boolean;
  items: ProjectRoi[];
}

/** GET /api/v1/indicators/roi/operacional — aceita mês único (competencia) ou intervalo acumulado. */
export async function fetchRoiOperacionalRanking(params?: {
  competencia?: string;
  dataInicial?: string;
  dataFinal?: string;
  scenario?: string;
}): Promise<RoiRanking> {
  const q: Record<string, string> = { scenario: params?.scenario ?? DEFAULT_SCENARIO_QUERY };
  if (params?.dataInicial) q.data_inicial = params.dataInicial;
  if (params?.dataFinal) q.data_final = params.dataFinal;
  if (!params?.dataInicial && !params?.dataFinal && params?.competencia) q.competencia = params.competencia;
  const { data } = await api.get<RoiRanking>("/indicators/roi/operacional", { params: q });
  return data;
}

/** GET /api/v1/indicators/roi/projetos/{project_id} */
export async function fetchProjectRoi(
  projectId: string,
  params?: { competencia?: string; scenario?: string },
): Promise<ProjectRoi> {
  const q: Record<string, string> = { scenario: params?.scenario ?? DEFAULT_SCENARIO_QUERY };
  if (params?.competencia) q.competencia = params.competencia;
  const { data } = await api.get<ProjectRoi>(`/indicators/roi/projetos/${projectId}`, { params: q });
  return data;
}

export interface ConsolidatedRoi {
  competencia: string;
  scenario: string;
  project_ids: string[];
  project_count: number;
  revenue: number;
  cost: number;
  operational_profit: number;
  roi: number | null;
  roi_pct: number | null;
}

/** GET /api/v1/indicators/roi/consolidado (perm: indicators.director) — mês único ou intervalo acumulado. */
export async function fetchConsolidatedRoi(params?: {
  competencia?: string;
  dataInicial?: string;
  dataFinal?: string;
  scenario?: string;
  projectIds?: string[];
}): Promise<ConsolidatedRoi> {
  const q: Record<string, string> = { scenario: params?.scenario ?? DEFAULT_SCENARIO_QUERY };
  if (params?.dataInicial) q.data_inicial = params.dataInicial;
  if (params?.dataFinal) q.data_final = params.dataFinal;
  if (!params?.dataInicial && !params?.dataFinal && params?.competencia) q.competencia = params.competencia;
  if (params?.projectIds && params.projectIds.length > 0) q.project_ids = params.projectIds.join(",");
  const { data } = await api.get<ConsolidatedRoi>("/indicators/roi/consolidado", { params: q });
  return data;
}

export interface RoiEvolutionPoint {
  competencia: string;
  revenue: number;
  cost: number;
  operational_profit: number;
  roi: number | null;
  roi_pct: number | null;
}

export interface RoiEvolution {
  scenario: string;
  project_ids: string[];
  points: RoiEvolutionPoint[];
}

/** GET /api/v1/indicators/roi/evolucao */
export async function fetchRoiEvolution(params: {
  dataInicial: string;
  dataFinal: string;
  scenario?: string;
  projectIds?: string[];
}): Promise<RoiEvolution> {
  const q: Record<string, string> = {
    data_inicial: params.dataInicial,
    data_final: params.dataFinal,
    scenario: params.scenario ?? DEFAULT_SCENARIO_QUERY,
  };
  if (params.projectIds && params.projectIds.length > 0) q.project_ids = params.projectIds.join(",");
  const { data } = await api.get<RoiEvolution>("/indicators/roi/evolucao", { params: q });
  return data;
}

export interface KpiCatalogEntry {
  code: string;
  name: string;
  status: "available" | "coming_soon";
}

/** GET /api/v1/indicators/catalog */
export async function fetchKpiCatalog(): Promise<KpiCatalogEntry[]> {
  const { data } = await api.get<{ items: KpiCatalogEntry[] }>("/indicators/catalog");
  return data.items;
}
