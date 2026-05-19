import { api } from "./api";

export type TipoFinanceiro = "endividamento" | "custo_fixo";
export type RenegotiationType = "UNIQUE" | "INSTALLMENTS";

export interface PagamentoMes {
  mes: string;
  valor: number;
}

export interface CompanyFinancialItem {
  id: string;
  tipo: string;
  item_type?: "MANUAL" | "COLABORADOR_MATRIZ" | null;
  employee_id?: string | null;
  employee_name?: string | null;
  employee_employment_type?: string | null;
  percentual?: number | null;
  nome: string;
  valor_referencia: number;
  category?: string | null;
  cost_center_ref?: string;
  cost_center: string;
  cost_center_project_id?: string | null;
  cost_center_system?: "ADMINISTRATIVO" | "FINANCEIRO" | null;
  description?: string | null;
  recurrence?: string | null;
  has_legal_process?: boolean;
  has_renegotiation?: boolean;
  renegotiated_amount?: number | null;
  renegotiation_type?: RenegotiationType | null;
  installment_count?: number | null;
  installment_value?: number | null;
  pagamentos: PagamentoMes[];
  total_pago: number;
  pago_mes: number;
  restante: number | null;
  progresso: number;
  status: string | null;
  progresso_mes: number | null;
}

export interface KpiEndividamento {
  total_endividamento: number;
  total_pago_mes: number;
  saldo_restante: number;
  quantidade_itens: number;
}

export interface KpiCustosFixos {
  total_esperado_mes: number;
  total_pago_mes: number;
  quantidade_itens: number;
}

export interface ChartPoint {
  mes: string;
  pagamentos_mes: number;
  saldo_restante_total: number | null;
}

export async function listCompanyFinanceItems(
  tipo: TipoFinanceiro,
  competencia: string,
): Promise<CompanyFinancialItem[]> {
  const { data } = await api.get<CompanyFinancialItem[]>("/company-finance/items/", {
    params: { tipo, competencia },
  });
  return data;
}

export async function createCompanyFinanceItem(payload: {
  tipo: TipoFinanceiro;
  nome: string;
  valor_referencia: number;
  category?: string | null;
  cost_center_ref: string;
  description?: string | null;
  recurrence?: string | null;
  item_type?: "MANUAL" | "COLABORADOR_MATRIZ";
  employee_id?: string | null;
  percentual?: number | null;
  has_legal_process?: boolean;
  has_renegotiation?: boolean;
  renegotiated_amount?: number | null;
  renegotiation_type?: RenegotiationType | null;
  installment_count?: number | null;
  installment_value?: number | null;
}): Promise<CompanyFinancialItem> {
  const { data } = await api.post<CompanyFinancialItem>("/company-finance/items/", payload);
  return data;
}

const CF_STRUCTURE_DEBUG = import.meta.env.DEV;

export async function updateCompanyFinanceItem(
  id: string,
  payload: {
    nome?: string;
    valor_referencia?: number;
    category?: string | null;
    cost_center_ref?: string;
    description?: string | null;
    recurrence?: string | null;
    item_type?: "MANUAL" | "COLABORADOR_MATRIZ";
    employee_id?: string | null;
    percentual?: number | null;
    has_legal_process?: boolean;
    has_renegotiation?: boolean;
    renegotiated_amount?: number | null;
    renegotiation_type?: RenegotiationType | null;
    installment_count?: number | null;
    installment_value?: number | null;
  },
  competencia: string,
): Promise<CompanyFinancialItem> {
  if (CF_STRUCTURE_DEBUG) {
    console.info("[company-finance] PATCH estrutura →", { id, competencia, payload });
  }
  const { data } = await api.patch<CompanyFinancialItem>(`/company-finance/items/${id}`, payload, {
    params: { competencia },
  });
  if (CF_STRUCTURE_DEBUG) {
    console.info("[company-finance] PATCH estrutura ←", data);
  }
  return data;
}

export async function deleteCompanyFinanceItem(id: string): Promise<void> {
  await api.delete(`/company-finance/items/${id}/`);
}

export async function replaceCompanyFinancePayments(
  id: string,
  pagamentos: PagamentoMes[],
  competencia: string,
): Promise<CompanyFinancialItem> {
  const { data } = await api.put<CompanyFinancialItem>(
    `/company-finance/items/${id}/payments/`,
    { pagamentos },
    { params: { competencia } },
  );
  return data;
}

export async function fetchKpiEndividamento(competencia: string): Promise<KpiEndividamento> {
  const { data } = await api.get<KpiEndividamento>("/company-finance/kpis/endividamento/", {
    params: { competencia },
  });
  return data;
}

export async function fetchKpiCustosFixos(competencia: string): Promise<KpiCustosFixos> {
  const { data } = await api.get<KpiCustosFixos>("/company-finance/kpis/custos-fixos/", {
    params: { competencia },
  });
  return data;
}

export async function fetchChartSeries(
  tipo: TipoFinanceiro,
  mes_inicio?: string,
  mes_fim?: string,
): Promise<{ points: ChartPoint[] }> {
  const { data } = await api.get<{ points: ChartPoint[] }>("/company-finance/chart-series/", {
    params: { tipo, mes_inicio, mes_fim },
  });
  return data;
}
