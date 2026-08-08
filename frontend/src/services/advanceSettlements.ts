import { api } from "./api";

// Contrato entregue pelo backend. O frontend NUNCA recalcula situação/residual/liquidado/etc. —
// tudo chega pronto (ver docs/ETAPA0_LIQUIDACAO_ANTECIPACOES.md §5.7).

export type FundingSource =
  | "SALDO_REPASSE"
  | "RECEBIMENTO_CLIENTE"
  | "ANTECIPACAO_DAYCOVAL"
  | "CAIXA_EMPRESA"
  | "OUTRA";

export type SituacaoLiquidacao =
  | "EM_ABERTO"
  | "PARCIALMENTE_LIQUIDADA"
  | "VENCIDA"
  | "LIQUIDADA";

/** Rótulos amigáveis — o usuário nunca vê Ledger/CAP/enum interno. */
export const FUNDING_SOURCE_LABELS: Record<FundingSource, string> = {
  SALDO_REPASSE: "Saldo do Repasse",
  RECEBIMENTO_CLIENTE: "Recebimento do Cliente",
  ANTECIPACAO_DAYCOVAL: "Antecipação Daycoval",
  CAIXA_EMPRESA: "Caixa da Empresa",
  OUTRA: "Outra",
};

export const FUNDING_SOURCE_OPTIONS: { value: FundingSource; label: string }[] = (
  Object.keys(FUNDING_SOURCE_LABELS) as FundingSource[]
).map((value) => ({ value, label: FUNDING_SOURCE_LABELS[value] }));

export const SITUACAO_META: Record<SituacaoLiquidacao, { label: string; cls: string }> = {
  EM_ABERTO: { label: "Em aberto", cls: "bg-slate-100 text-slate-700 ring-slate-200" },
  PARCIALMENTE_LIQUIDADA: { label: "Parcialmente liquidada", cls: "bg-amber-100 text-amber-900 ring-amber-200" },
  VENCIDA: { label: "Vencida", cls: "bg-red-100 text-red-800 ring-red-200" },
  LIQUIDADA: { label: "Liquidada", cls: "bg-emerald-100 text-emerald-900 ring-emerald-200" },
};

export interface SettlementMovement {
  id: string;
  batch_item_id: string;
  event_id: string | null;
  amount: number;
  funding_source: FundingSource;
  settled_at: string;
  observation: string | null;
  reversed_at: string | null;
  reversal_reason: string | null;
  created_at: string;
}

/** Obrigação (participação NF × operação) — todos os totais e a situação vêm do backend. */
export interface Obligation {
  batch_item_id: string;
  batch_id: string;
  invoice_id: string;
  institution_id: string | null;
  institution: string | null;
  institution_profile: string | null;
  sgc_number: number;
  invoice_number: string | null;
  client_name: string | null;
  project_name: string | null;
  valor_total: number;
  valor_liquidado: number;
  valor_residual: number;
  situacao: SituacaoLiquidacao;
  vencimento: string | null;
  dias_em_atraso: number;
  origens_resumo: string;
  movimentacoes: SettlementMovement[];
}

export interface SettlementKpis {
  nfs_pendentes: number;
  nfs_vencidas: number;
  valor_total_vencido: number;
  total_liquidado: number;
  saldo_repasse: number;
}

export interface SettlementMovementInput {
  funding_source: FundingSource;
  amount: number;
  settled_at?: string | null;
  observation?: string | null;
}

export interface ObligationFilters {
  institution_id?: string | null;
  invoice_number?: string | null;
  sgc_number?: number | null;
  situacao?: SituacaoLiquidacao | null;
}

export async function fetchObligations(filters: ObligationFilters = {}): Promise<Obligation[]> {
  const params: Record<string, string | number> = {};
  if (filters.institution_id) params.institution_id = filters.institution_id;
  if (filters.invoice_number) params.invoice_number = filters.invoice_number;
  if (filters.sgc_number != null) params.sgc_number = filters.sgc_number;
  if (filters.situacao) params.situacao = filters.situacao;
  const { data } = await api.get<Obligation[]>("/invoices/advance-settlements", { params });
  return data;
}

export async function fetchSettlementKpis(institutionId?: string | null): Promise<SettlementKpis> {
  const params = institutionId ? { institution_id: institutionId } : undefined;
  const { data } = await api.get<SettlementKpis>("/invoices/advance-settlements/kpis", { params });
  return data;
}

export async function createSettlement(
  batchItemId: string,
  movements: SettlementMovementInput[],
): Promise<Obligation> {
  const { data } = await api.post<Obligation>("/invoices/advance-settlements", {
    batch_item_id: batchItemId,
    movements,
  });
  return data;
}

// --- Indicadores gerenciais (Fase 3) — tudo computado no backend ---

export interface OrigemDistribuicao {
  funding_source: FundingSource;
  label: string;
  total: number;
  pct: number;
}

export interface ManagementSummary {
  valor_ainda_antecipado: number;
  valor_vencido: number;
  valor_a_vencer_30d: number;
  tempo_medio_liquidacao_dias: number | null;
  liquidado_repasse: number;
  liquidado_outras_origens: number;
  total_liquidado: number;
  distribuicao_origens: OrigemDistribuicao[];
}

export interface TimelineEvent {
  date: string;
  tipo: string; // ANTECIPADA | VENCEU | LIQUIDACAO
  label: string;
  amount: number | null;
  origem: string | null;
  estornada: boolean;
  evento_number: number | null;
}

export interface Timeline {
  batch_item_id: string;
  situacao: SituacaoLiquidacao;
  events: TimelineEvent[];
}

export async function fetchManagementSummary(institutionId?: string | null): Promise<ManagementSummary> {
  const params = institutionId ? { institution_id: institutionId } : undefined;
  const { data } = await api.get<ManagementSummary>("/invoices/advance-settlements/management-summary", { params });
  return data;
}

export async function fetchTimeline(batchItemId: string): Promise<Timeline> {
  const { data } = await api.get<Timeline>(`/invoices/advance-settlements/${batchItemId}/timeline`);
  return data;
}

export async function reverseMovement(movementId: string, reason?: string): Promise<Obligation> {
  const { data } = await api.delete<Obligation>(`/invoices/advance-settlement-movements/${movementId}`, {
    params: reason ? { reason } : undefined,
  });
  return data;
}

// --- Eventos de Liquidação (pagamentos) — Liquidação em Massa + Extrato de Liquidações ---

export type SettlementEventStatus = "ACTIVE" | "PARTIALLY_REVERSED" | "FULLY_REVERSED";
export type SettlementCreationSource = "MANUAL" | "MASS";

/** Evento de Liquidação — dados estruturados; o código/descrição vêm do presenter TS. */
export interface SettlementEvent {
  id: string;
  number: number;
  code: string;
  creation_source: SettlementCreationSource;
  status: SettlementEventStatus;
  institution_id: string | null;
  institution: string | null;
  payment_date: string;
  funding_source: FundingSource | null;
  funding_source_label: string | null;
  total_amount: number;
  invoice_count: number;
  nf_numbers: string[];
  created_by_name: string | null;
  created_at: string;
}

export interface SettlementEventMovement {
  id: string;
  nf_number: string | null;
  client_name: string | null;
  amount: number;
  funding_source: FundingSource;
  funding_source_label: string;
  observation: string | null;
  reversed_at: string | null;
}

export interface SettlementEventDetail extends SettlementEvent {
  movimentacoes: SettlementEventMovement[];
}

export interface MassSettlementLineInput {
  batch_item_id: string;
  amount: number;
}

export interface MassSettlementInput {
  funding_source: FundingSource;
  payment_date?: string | null;
  observation?: string | null;
  lines: MassSettlementLineInput[];
}

export interface MassSettlementResult {
  event: SettlementEvent;
  obligations: Obligation[];
}

export async function createMassSettlement(input: MassSettlementInput): Promise<MassSettlementResult> {
  const { data } = await api.post<MassSettlementResult>("/invoices/advance-settlement-events", input);
  return data;
}

export async function fetchSettlementEvents(institutionId?: string | null): Promise<SettlementEvent[]> {
  const params = institutionId ? { institution_id: institutionId } : undefined;
  const { data } = await api.get<SettlementEvent[]>("/invoices/advance-settlement-events", { params });
  return data;
}

export async function fetchSettlementEventDetail(eventId: string): Promise<SettlementEventDetail> {
  const { data } = await api.get<SettlementEventDetail>(`/invoices/advance-settlement-events/${eventId}`);
  return data;
}
