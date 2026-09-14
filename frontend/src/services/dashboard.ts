import { api } from "./api";

/** Padrão de API quando o cenário não é informado (alinhado ao backend). */
const DEFAULT_SCENARIO_QUERY = "REALIZADO";

/** null = percentual de reserva (sem regime cadastrado); "MISTO" = período com regimes diferentes. */
export type TaxRegime = "LUCRO_PRESUMIDO" | "LUCRO_REAL" | "MISTO";

/**
 * Origem do custo de antecipação:
 * REAL = custo real das operações do mês seguinte; PARCIAL = idem, mês seguinte em andamento;
 * MEDIA = média ponderada dos meses fechados (projeção); FIXA = percentual fixo das Configurações;
 * MISTO = período com meses de origens diferentes.
 */
export type AnticipationSource = "REAL" | "PARCIAL" | "MEDIA" | "FIXA" | "MISTO";

/** Campos do motor de custos por regime / valores pagos (comuns ao resumo e à série mensal). */
export interface ProjectCostDetail {
  /**
   * Custo da antecipação (R$) por instituição (nome de exibição); soma = anticipation_amount.
   * Vazio/null quando a taxa é a fixa (sem divisão disponível).
   */
  anticipation_by_institution?: Record<string, number> | null;
  anticipation_source?: AnticipationSource | null;
  /** Mês fechado: mão de obra = folha efetivamente paga no CAP; false = estimativa pelo cadastro. */
  labor_real?: boolean;
  /** Mês fechado: veículos = parte do projeto na fatura da frota paga; false = lançado pelos gestores. */
  vehicle_real?: boolean;
  tax_regime?: TaxRegime | null;
  tax_pis?: number | null;
  tax_cofins?: number | null;
  tax_iss?: number | null;
  /** No Lucro Real é 0 aqui (incide sobre o lucro da empresa). */
  tax_irpj?: number | null;
  tax_csll?: number | null;
}

export interface DirectorSummary extends ProjectCostDetail {
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
  /** Receita − operacional total − rateio/overhead */
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
  /** Antecipação ainda pode subir: as operações do mês seguinte estão em andamento. */
  anticipation_partial?: boolean;
}

export interface MonthlyPoint extends ProjectCostDetail {
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
  /** Antecipação ainda pode subir: as operações do mês seguinte estão em andamento. */
  anticipation_partial?: boolean;
}

export interface FinancialDashboardSummary {
  scenario?: string;
  summary: DirectorSummary;
  monthly_series: MonthlyPoint[];
  monthly_series_previsto?: MonthlyPoint[];
  monthly_series_realizado?: MonthlyPoint[];
  period_start?: string;
  period_end?: string;
  month_count?: number;
  /** Lucro líquido (`net_profit`) na competência — cenário PREVISTO */
  lucro_liquido_previsto?: number;
  /** Lucro líquido (`net_profit`) na competência — cenário REALIZADO */
  lucro_liquido_realizado?: number;
}

export async function fetchFinancialSummary(params: {
  /** Mês único ou âncora para “últimos N meses” (primeiro dia do mês, YYYY-MM-DD) */
  competencia?: string;
  start_date?: string;
  end_date?: string;
  /** Últimos N meses terminando em `competencia` (ou mês atual se omitido) */
  months?: number;
  /** Omitir ou vazio = consolidado global (ADMIN ou CONSULTA; GESTOR deve informar projeto) */
  project_id?: string;
  /** PREVISTO ou REALIZADO */
  scenario?: string;
}): Promise<FinancialDashboardSummary> {
  const q: Record<string, string | number> = {};
  if (params.competencia != null) q.competencia = params.competencia;
  if (params.start_date != null) q.start_date = params.start_date;
  if (params.end_date != null) q.end_date = params.end_date;
  if (params.months != null) q.months = params.months;
  if (params.project_id) q.project_id = params.project_id;
  q.scenario = params.scenario ?? DEFAULT_SCENARIO_QUERY;
  const { data } = await api.get<FinancialDashboardSummary>("/dashboard/summary/", { params: q });
  return data;
}

/** Linha por projeto para os gráficos “por projeto” do dashboard operacional. */
export interface ProjectBreakdownRow {
  projectId: string;
  name: string;
  /** Receita do cenário ativo (total_revenue) no período/filtro selecionado. */
  revenue: number;
  /** Custo operacional total do cenário ativo (operational_cost) no período/filtro. */
  operationalCost: number;
}

/**
 * Constrói a quebra por projeto reaproveitando o endpoint `/dashboard/summary/`
 * (um request por projeto, mesmo cenário/período/competência do dashboard).
 * Somar estas linhas reproduz exatamente os cards consolidados — nenhuma regra
 * financeira é recalculada no front; apenas reagrupamos os valores existentes.
 */
export async function fetchProjectsBreakdown(
  projects: ReadonlyArray<{ id: string; name: string }>,
  base: { competencia?: string; start_date?: string; end_date?: string; months?: number },
  scenario: string,
): Promise<ProjectBreakdownRow[]> {
  return Promise.all(
    projects.map(async (p) => {
      const data = await fetchFinancialSummary({ ...base, project_id: p.id, scenario });
      const s = data.summary;
      return {
        projectId: p.id,
        name: p.name,
        revenue: s.total_revenue ?? s.revenue_total,
        operationalCost: s.operational_cost ?? 0,
      };
    }),
  );
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
  /** Antecipação ainda pode subir: as operações do mês seguinte estão em andamento. */
  anticipation_partial?: boolean;
}

export interface ProjectDashboardResponse {
  summary: ProjectSummary;
  monthly_series: MonthlyPoint[];
  monthly_series_previsto?: MonthlyPoint[];
  monthly_series_realizado?: MonthlyPoint[];
  period_start?: string;
  period_end?: string;
  month_count?: number;
}

export async function fetchProjectFinancialDashboard(
  projectId: string,
  params?: {
    competencia?: string;
    start_date?: string;
    end_date?: string;
    months?: number;
    scenario?: string;
  }
): Promise<ProjectDashboardResponse> {
  const q: Record<string, string | number> = { scenario: params?.scenario ?? DEFAULT_SCENARIO_QUERY };
  if (params?.competencia != null) q.competencia = params.competencia;
  if (params?.start_date != null) q.start_date = params.start_date;
  if (params?.end_date != null) q.end_date = params.end_date;
  if (params?.months != null) q.months = params.months;
  const { data } = await api.get<ProjectDashboardResponse>(`/dashboard/project/${projectId}/`, { params: q });
  return data;
}
