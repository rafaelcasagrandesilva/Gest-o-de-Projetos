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
  /** Endividamento de ex-colaborador: pessoa do cadastro do Jurídico (`legal_persons`). */
  legal_person_id?: string | null;
  legal_person_name?: string | null;
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
  /** Modo do endividamento: false = parcelas iguais (atual); true = cronograma personalizado. */
  uses_custom_schedule?: boolean;
  /** Execução oficial da dívida no Modo 2 (fonte única). `null` no Modo 1. Só EXIBIR. */
  schedule?: ScheduleExecution | null;
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
  /** Só Endividamento: vínculo com um desligado do Jurídico. Excludente com `employee_id`. */
  legal_person_id?: string | null;
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
    legal_person_id?: string | null;
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
    uses_custom_schedule?: boolean;
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
    // `zero_explicito` diz ao servidor que este cliente distingue caixa vazia (null) de
    // zero digitado (0). Sem a flag, o servidor mantém o comportamento antigo (0 = limpar)
    // — é o que protege quem estiver com o JS anterior em cache.
    { pagamentos, zero_explicito: true },
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

/* ------------------------------------------------------------------ *
 * Cronograma Financeiro Personalizado (Endividamento — Modo 2)
 * Contrato de LEITURA: o backend é a fonte única. O frontend só exibe.
 * ------------------------------------------------------------------ */

/** Execução oficial da dívida (aninhada no item). Todos os números vêm do backend. */
export interface ScheduleExecution {
  total_negociado: number;
  total_cronograma: number;
  total_pago: number;
  saldo_restante: number;
  /** Fração 0–1. */
  progresso: number;
  parcelas_total: number;
  parcelas_pagas: number;
  parcelas_restantes: number;
  proxima_vencimento: string | null;
  proxima_valor: number | null;
  ultima_vencimento: string | null;
  data_encerramento: string | null;
}

/** Uma parcela do cronograma (com espelho de pagamento do CAP). */
export interface ScheduleLineRead {
  id: string;
  seq: number | null;
  vencimento: string | null; // YYYY-MM-DD
  valor: number | null;
  descricao: string | null;
  cap_amount_paid?: number | null;
  cap_status?: "ABERTO" | "PARCIAL" | "PAGO" | null;
  has_payment?: boolean;
}

/** Cronograma completo + fechamento (GET /schedule). */
export interface ScheduleRead {
  item_id: string;
  uses_custom_schedule: boolean;
  renegotiated_amount: number | null;
  total_cronograma: number | null;
  diferenca: number | null;
  is_valid: boolean;
  data_encerramento: string | null;
  lines: ScheduleLineRead[];
  payable_sync_warning?: string | null;
}

/** Faixa do gerador (expansão pelo backend). */
export interface ScheduleRangeInput {
  seq_start: number;
  seq_end: number;
  valor: number;
  dia: number;
  primeiro_vencimento: string; // YYYY-MM-DD
}

export interface SchedulePreviewLine {
  seq: number;
  vencimento: string; // YYYY-MM-DD
  valor: number;
  descricao: string | null;
}

export interface SchedulePreview {
  lines: SchedulePreviewLine[];
  count: number;
  total: number;
}

/** Carga de uma parcela no PUT (id ausente = nova). `seq` preserva parcelas pagas ao regerar. */
export interface ScheduleLineInput {
  id?: string | null;
  seq: number;
  vencimento: string; // YYYY-MM-DD
  valor: number;
  descricao?: string | null;
}

export async function fetchSchedule(itemId: string): Promise<ScheduleRead> {
  const { data } = await api.get<ScheduleRead>(`/company-finance/items/${itemId}/schedule`);
  return data;
}

export async function previewSchedule(
  itemId: string,
  ranges: ScheduleRangeInput[],
): Promise<SchedulePreview> {
  const { data } = await api.post<SchedulePreview>(
    `/company-finance/items/${itemId}/schedule/preview`,
    { ranges },
  );
  return data;
}

export async function replaceSchedule(
  itemId: string,
  lines: ScheduleLineInput[],
  allowUnbalanced = false,
): Promise<ScheduleRead> {
  const { data } = await api.put<ScheduleRead>(`/company-finance/items/${itemId}/schedule`, {
    lines,
    allow_unbalanced: allowUnbalanced,
  });
  return data;
}

// --- Motor de saldo (Endividamento) ---------------------------------------------------- //
// O razão é DERIVADO a cada leitura no backend (principal + vigências de taxa + eventos + a
// grade mensal de pagamentos). O frontend só consome — nenhuma regra financeira mora aqui.

export interface DebtLedgerLine {
  competencia: string; // "AAAA-MM-01"
  saldo_inicial: number;
  aporte: number;
  abatimento: number;
  encargo_manual: number;
  taxa: number; // decimal ao mês: 0.015 = 1,5% a.m.
  encargo: number;
  pagamento: number;
  /** Parte do pagamento vinda de Retirada de Repasse — não editável (vem do Ledger). */
  pagamento_repasse: number;
  juros_pagos: number;
  amortizacao: number;
  saldo_final: number;
  encargo_acumulado: number;
  is_projected: boolean;
}

export interface DebtLedgerSummary {
  principal: number;
  total_aportes: number;
  total_abatimentos: number;
  total_contratado: number;
  total_encargos: number;
  encargos_pagos: number;
  encargos_capitalizados: number;
  total_pago: number;
  total_amortizado: number;
  saldo_atual: number;
  taxa_vigente: number;
  competencia_final: string | null;
  /** Hipótese ("se ninguém pagar"), separada do saldo atual, que é fato. */
  saldo_projetado: number | null;
  competencia_projecao: string | null;
}

export interface DebtRate {
  id: string;
  valid_from: string;
  monthly_rate: number;
  note: string | null;
}

export type DebtEventKind = "APORTE" | "ABATIMENTO" | "ENCARGO_MANUAL";

export interface DebtEvent {
  id: string;
  competencia: string;
  kind: DebtEventKind;
  amount: number;
  description: string | null;
}

export interface DebtLedger {
  item_id: string;
  nome: string;
  origem: string;
  /** false = dívida congelada (nenhuma vigência com taxa > 0). */
  tem_correcao: boolean;
  /** true = a taxa exibida é o padrão do SGC, e não uma vigência desta dívida. */
  usando_taxa_padrao: boolean;
  linhas: DebtLedgerLine[];
  resumo: DebtLedgerSummary;
  taxas: DebtRate[];
  eventos: DebtEvent[];
  payable_sync_warning?: string | null;
}

/** Uma linha da planilha de evolução como o usuário a edita: cada campo é uma caixa da linha. */
export interface DebtLedgerRowInput {
  competencia: string;
  /** Decimal ao mês. Preenchida cria a vigência NAQUELE mês; vazia herda; zero congela. */
  taxa?: number | null;
  aporte?: number | null;
  abatimento?: number | null;
  encargo_manual?: number | null;
  /** `null` = caixa vazia (limpa o lançamento); `0` = zero declarado. */
  pagamento?: number | null;
}

export interface DebtLedgerReplaceInput {
  start_month?: string | null;
  principal?: number | null;
  linhas: DebtLedgerRowInput[];
}

/** Recalcula a evolução a partir do que está digitado, sem gravar. */
export async function previewDebtLedger(
  itemId: string,
  payload: DebtLedgerReplaceInput,
  projecao = 6,
): Promise<DebtLedger> {
  const { data } = await api.post<DebtLedger>(
    `/company-finance/items/${itemId}/ledger/preview`,
    payload,
    { params: { projecao } },
  );
  return data;
}

/** Salva a planilha inteira: início, taxas, aportes e pagamentos numa transação. */
export async function replaceDebtLedger(
  itemId: string,
  payload: DebtLedgerReplaceInput,
  projecao = 6,
): Promise<DebtLedger> {
  const { data } = await api.put<DebtLedger>(
    `/company-finance/items/${itemId}/ledger`,
    payload,
    { params: { projecao } },
  );
  return data;
}

export async function fetchDebtLedger(itemId: string, projecao = 6): Promise<DebtLedger> {
  const { data } = await api.get<DebtLedger>(`/company-finance/items/${itemId}/ledger`, {
    params: { projecao },
  });
  return data;
}

export async function setDebtRate(
  itemId: string,
  payload: { valid_from: string; monthly_rate: number; note?: string | null },
): Promise<DebtLedger> {
  const { data } = await api.put<DebtLedger>(`/company-finance/items/${itemId}/rates`, payload);
  return data;
}

export async function deleteDebtRate(itemId: string, rateId: string): Promise<DebtLedger> {
  const { data } = await api.delete<DebtLedger>(`/company-finance/items/${itemId}/rates/${rateId}`);
  return data;
}

export async function addDebtEvent(
  itemId: string,
  payload: { competencia: string; kind: DebtEventKind; amount: number; description?: string | null },
): Promise<DebtLedger> {
  const { data } = await api.post<DebtLedger>(`/company-finance/items/${itemId}/events`, payload);
  return data;
}

export async function deleteDebtEvent(itemId: string, eventId: string): Promise<DebtLedger> {
  const { data } = await api.delete<DebtLedger>(`/company-finance/items/${itemId}/events/${eventId}`);
  return data;
}

/** Gerador de parcelas da Evolução (o caso "parcelas fixas COM juros rodando"). */
export type DebtPlanMode = "AMORT_FIXA" | "PARCELA_FIXA" | "N_PARCELAS";

export interface DebtPlanLine {
  competencia: string;
  juros: number;
  amortizacao: number;
  valor: number;
  saldo_final: number;
}

export interface DebtPlan {
  saldo_base: number;
  competencia_inicial: string;
  total_pago: number;
  total_juros: number;
  parcelas: DebtPlanLine[];
}

export async function planDebtInstallments(
  itemId: string,
  payload: { start_month: string; mode: DebtPlanMode; amount?: number | null; count?: number | null },
): Promise<DebtPlan> {
  const { data } = await api.post<DebtPlan>(`/company-finance/items/${itemId}/ledger/plan`, payload);
  return data;
}
