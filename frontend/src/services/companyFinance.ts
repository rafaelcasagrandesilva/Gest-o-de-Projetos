import { api } from "./api";

export type TipoFinanceiro = "endividamento" | "custo_fixo";
export type RenegotiationType = "UNIQUE" | "INSTALLMENTS";

export interface PagamentoMes {
  mes: string;
  /** `null` quando redigido por falta de "Dados sensíveis". */
  valor: number | null;
  /** Quantidade de lançamentos que compõem o valor do mês (>1 → detalhe no modal). */
  count?: number | null;
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
  /** Descrição própria do item (identificador da dívida em Endividamento). */
  item_description?: string | null;
  valor_referencia: number;
  /** Base financeira ÚNICA da dívida (renegociado válido > 0 senão valor_referencia). */
  debt_base?: number;
  category?: string | null;
  cost_center_ref?: string;
  cost_center: string;
  cost_center_project_id?: string | null;
  cost_center_system?: "ADMINISTRATIVO" | "FINANCEIRO" | "ALMOXARIFADO" | "RH" | null;
  description?: string | null;
  recurrence?: string | null;
  is_monthly_required?: boolean;
  has_legal_process?: boolean;
  has_renegotiation?: boolean;
  renegotiated_amount?: number | null;
  renegotiation_type?: RenegotiationType | null;
  installment_count?: number | null;
  installment_value?: number | null;
  renegotiation_agreement_date?: string | null;
  renegotiation_first_payment_date?: string | null;
  renegotiation_due_day?: number | null;
  /** Ciclo de vida do cadastro (distinto de `status`, que é o progresso do endividamento). */
  is_active?: boolean;
  start_date?: string | null;
  end_date?: string | null;
  pagamentos: PagamentoMes[];
  total_pago: number | null;
  pago_mes: number | null;
  restante: number | null;
  /** Fração 0–1 do progresso de pagamento. Redigido (null) sem a permissão sensível. */
  progresso: number | null;
  status: string | null;
  progresso_mes: number | null;
  /** Espelho do Contas a Pagar da competência (fonte oficial de pagamento/status). */
  cap_has_line?: boolean;
  cap_amount_paid?: number;
  cap_status?: "ABERTO" | "PARCIAL" | "PAGO" | null;
  cap_is_obsolete?: boolean;
  /** Aviso da sincronização grade→CAP (só na resposta do PUT de pagamentos). */
  payable_sync_warning?: string | null;
}

export interface KpiEndividamento {
  total_endividamento: number | null;
  total_pago_mes: number | null;
  saldo_restante: number | null;
  quantidade_itens: number;
}

export interface KpiCustosFixos {
  total_esperado_mes: number | null;
  total_pago_mes: number | null;
  quantidade_itens: number;
}

export interface PendenciaLancamento {
  item_id: string;
  nome: string;
  competencia: string;
  category?: string | null;
  cost_center?: string | null;
  valor_referencia: number;
  ultimo_valor?: number | null;
  ultimo_mes?: string | null;
  origem?: "manual" | "renegociacao";
}

export interface PendenciasCustosFixos {
  competencia: string;
  quantidade: number;
  pendencias: PendenciaLancamento[];
  total_previsto?: number;
  total_pago?: number;
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
  /** Opcional em Endividamento (composto no backend a partir de colaborador + descrição). */
  nome?: string;
  item_description?: string | null;
  valor_referencia: number | null;
  category?: string | null;
  cost_center_ref: string;
  description?: string | null;
  recurrence?: string | null;
  item_type?: "MANUAL" | "COLABORADOR_MATRIZ";
  employee_id?: string | null;
  percentual?: number | null;
  is_monthly_required?: boolean;
  has_legal_process?: boolean;
  has_renegotiation?: boolean;
  renegotiated_amount?: number | null;
  renegotiation_type?: RenegotiationType | null;
  installment_count?: number | null;
  installment_value?: number | null;
  renegotiation_agreement_date?: string | null;
  renegotiation_first_payment_date?: string | null;
  renegotiation_due_day?: number | null;
  is_active?: boolean;
  /** Ciclo de vida — início obrigatório em novos cadastros; encerramento opcional. */
  start_date: string;
  end_date?: string | null;
}): Promise<CompanyFinancialItem> {
  const { data } = await api.post<CompanyFinancialItem>("/company-finance/items/", payload);
  return data;
}

const CF_STRUCTURE_DEBUG = import.meta.env.DEV;

export async function updateCompanyFinanceItem(
  id: string,
  payload: {
    nome?: string;
    item_description?: string | null;
    valor_referencia?: number;
    category?: string | null;
    cost_center_ref?: string;
    description?: string | null;
    recurrence?: string | null;
    item_type?: "MANUAL" | "COLABORADOR_MATRIZ";
    employee_id?: string | null;
    percentual?: number | null;
    is_monthly_required?: boolean;
    has_legal_process?: boolean;
    has_renegotiation?: boolean;
    renegotiated_amount?: number | null;
    renegotiation_type?: RenegotiationType | null;
    installment_count?: number | null;
    installment_value?: number | null;
    renegotiation_agreement_date?: string | null;
    renegotiation_first_payment_date?: string | null;
    renegotiation_due_day?: number | null;
    is_active?: boolean;
    start_date?: string | null;
    end_date?: string | null;
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
  if (CF_STRUCTURE_DEBUG) {
    console.info("[company-finance] PUT pagamentos →", { id, competencia, pagamentos });
  }
  const { data } = await api.put<CompanyFinancialItem>(
    `/company-finance/items/${id}/payments`,
    { pagamentos },
    { params: { competencia } },
  );
  if (CF_STRUCTURE_DEBUG) {
    console.info("[company-finance] PUT pagamentos ←", data);
  }
  return data;
}

/** Um lançamento (entrada) de uma competência. Genérico para qualquer item de Custo Fixo. */
export interface LancamentoCompetencia {
  id: string;
  competencia: string;
  /** YYYY-MM-DD. */
  vencimento: string | null;
  /** `null` quando redigido por falta de "Dados sensíveis". */
  valor: number | null;
  descricao: string | null;
  /** Espelho do CAP (pagamento por lançamento). */
  cap_amount_paid?: number | null;
  cap_status?: "ABERTO" | "PARCIAL" | "PAGO" | null;
  has_payment?: boolean;
}

export interface LancamentosCompetencia {
  item_id: string;
  competencia: string;
  lancamentos: LancamentoCompetencia[];
  total: number | null;
  payable_sync_warning?: string | null;
}

/** Carga de um lançamento no PUT (id ausente = novo). */
export interface LancamentoCompetenciaInput {
  id?: string | null;
  vencimento?: string | null;
  valor: number;
  descricao?: string | null;
}

export async function fetchCompanyFinanceEntries(
  itemId: string,
  competencia: string,
): Promise<LancamentosCompetencia> {
  const { data } = await api.get<LancamentosCompetencia>(
    `/company-finance/items/${itemId}/entries`,
    { params: { competencia } },
  );
  return data;
}

export async function replaceCompanyFinanceEntries(
  itemId: string,
  competencia: string,
  lancamentos: LancamentoCompetenciaInput[],
): Promise<LancamentosCompetencia> {
  const { data } = await api.put<LancamentosCompetencia>(
    `/company-finance/items/${itemId}/entries`,
    { lancamentos },
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

export async function fetchPendenciasCustosFixos(
  competencia: string,
): Promise<PendenciasCustosFixos> {
  const { data } = await api.get<PendenciasCustosFixos>("/company-finance/pendencias/custos-fixos/", {
    params: { competencia },
  });
  return data;
}

/** Pendências de lançamento por tipo (custo_fixo manual; endividamento manual + renegociação). */
export async function fetchPendencias(
  tipo: TipoFinanceiro,
  competencia: string,
): Promise<PendenciasCustosFixos> {
  const { data } = await api.get<PendenciasCustosFixos>("/company-finance/pendencias/", {
    params: { tipo, competencia },
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
