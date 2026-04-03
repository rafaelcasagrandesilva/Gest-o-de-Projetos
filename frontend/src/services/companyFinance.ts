import { api } from "./api";

export type TipoFinanceiro = "endividamento" | "custo_fixo";

export interface PagamentoMes {
  mes: string;
  valor: number;
}

export interface CompanyFinancialItem {
  id: string;
  tipo: string;
  nome: string;
  valor_referencia: number;
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
  const { data } = await api.get<CompanyFinancialItem[]>("/company-finance/items", {
    params: { tipo, competencia },
  });
  return data;
}

export async function createCompanyFinanceItem(payload: {
  tipo: TipoFinanceiro;
  nome: string;
  valor_referencia: number;
}): Promise<CompanyFinancialItem> {
  const { data } = await api.post<CompanyFinancialItem>("/company-finance/items", payload);
  return data;
}

export async function updateCompanyFinanceItem(
  id: string,
  payload: { nome?: string; valor_referencia?: number },
  competencia: string,
): Promise<CompanyFinancialItem> {
  const { data } = await api.patch<CompanyFinancialItem>(`/company-finance/items/${id}`, payload, {
    params: { competencia },
  });
  return data;
}

export async function deleteCompanyFinanceItem(id: string): Promise<void> {
  await api.delete(`/company-finance/items/${id}`);
}

export async function replaceCompanyFinancePayments(
  id: string,
  pagamentos: PagamentoMes[],
  competencia: string,
): Promise<CompanyFinancialItem> {
  const { data } = await api.put<CompanyFinancialItem>(
    `/company-finance/items/${id}/payments`,
    { pagamentos },
    { params: { competencia } },
  );
  return data;
}

export async function fetchKpiEndividamento(competencia: string): Promise<KpiEndividamento> {
  const { data } = await api.get<KpiEndividamento>("/company-finance/kpis/endividamento", {
    params: { competencia },
  });
  return data;
}

export async function fetchKpiCustosFixos(competencia: string): Promise<KpiCustosFixos> {
  const { data } = await api.get<KpiCustosFixos>("/company-finance/kpis/custos-fixos", {
    params: { competencia },
  });
  return data;
}

export async function fetchChartSeries(
  tipo: TipoFinanceiro,
  mes_inicio?: string,
  mes_fim?: string,
): Promise<{ points: ChartPoint[] }> {
  const { data } = await api.get<{ points: ChartPoint[] }>("/company-finance/chart-series", {
    params: { tipo, mes_inicio, mes_fim },
  });
  return data;
}
