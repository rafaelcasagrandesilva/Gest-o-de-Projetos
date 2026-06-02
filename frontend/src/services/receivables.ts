import { api } from "./api";

export type InvoiceStatus = "EMITIDA" | "ANTECIPADA" | "RECEBIDA" | "CANCELADA";

/** Alinha com query `period_field` da API: emissão ou vencimento. */
export type PeriodField = "issue" | "due";

export interface ReceivableInvoice {
  id: string;
  created_at: string;
  updated_at: string;
  project_id: string;
  project_name: string | null;
  number: string;
  issue_date: string;
  due_days: number;
  due_date: string;
  gross_amount: number;
  net_amount: number;
  client_name: string | null;
  notes: string | null;
  is_anticipated: boolean;
  institution: string | null;
  advance_amount_received: number | null;
  advance_amount_due: number | null;
  advance_due_date: string | null;
  received_amount: number;
  received_date: string | null;
  interest_amount: number;
  advance_cost_value: number | null;
  advance_interest_rate: number | null;
  advance_monthly_rate: number | null;
  implied_monthly_rate_percent: number | null;
  anticipations?: InvoiceAnticipation[];
  status: InvoiceStatus;
  has_pdf: boolean;
  pdf_url: string | null;
  activity_log: string | null;
  include_in_dashboard: boolean;
  advance_batch_id?: string | null;
  advance_batch?: AdvanceBatchSummary | null;
}

export interface AdvanceBatchSummary {
  id: string;
  batch_number: string;
  institution: string;
  status: string;
}

export interface InvoiceAnticipation {
  id: string;
  invoice_id: string;
  institution: string;
  amount_received: number;
  amount_to_repay: number;
  data_recebimento: string;
  due_date: string;
  created_at: string;
  updated_at: string;
  juros_total?: number | null;
  taxa_percentual?: number | null;
  taxa_mensal?: number | null;
  dias?: number | null;
  include_in_dashboard?: boolean;
}

export interface ReceivableKpis {
  total_a_receber: number;
  total_bruto_a_receber: number;
  recebido_no_mes: number;
  em_atraso_valor: number;
  total_nfs: number;
}

export async function fetchReceivableInvoices(params: {
  project_id?: string;
  status?: InvoiceStatus;
  client?: string;
  period_field?: PeriodField;
  year?: number;
  month?: number;
}): Promise<ReceivableInvoice[]> {
  // NFs (CRUD) seguem no módulo dedicado de invoices
  const { data } = await api.get<ReceivableInvoice[]>("/invoices/", { params });
  return data;
}

export async function fetchReceivableKpis(params: {
  project_id?: string;
  year?: number;
  month?: number;
  period_field?: PeriodField;
}): Promise<ReceivableKpis> {
  const { data } = await api.get<ReceivableKpis>("/invoices/kpis/", { params });
  return data;
}

export type ReceivableViewStatus = "ABERTO" | "PARCIAL" | "RECEBIDO";
export type ReceivableViewType = "NF" | "MANUAL" | "ANTECIPACAO" | "BORDERO";

export interface ReceivableViewRow {
  id: string;
  created_at: string;
  updated_at: string;
  tipo?: ReceivableViewType;
  client: string | null;
  number: string;
  descricao?: string | null;
  numero_referencia?: string | null;
  issue_date: string;
  due_date: string;
  received_at?: string | null;
  net_value: number;
  amount_received_advance: number;
  amount_received_customer: number;
  total_received: number;
  remaining: number;
  status: ReceivableViewStatus;
  /** Preenchido quando a NF está cancelada (visível só com invoices.reactivate). */
  invoice_status?: InvoiceStatus | null;
  observacao?: string | null;
  include_in_dashboard?: boolean;
}

export async function fetchReceivablesView(params: {
  project_id?: string;
  status?: InvoiceStatus; // filtra via status efetivo da NF na API
  client?: string;
  tipo?: ReceivableViewType;
  period_field?: PeriodField;
  year?: number;
  month?: number;
}): Promise<ReceivableViewRow[]> {
  const { data } = await api.get<ReceivableViewRow[]>("/financial/receivables/", { params });
  return data;
}

export interface ReceivableManualItem {
  id: string;
  created_at: string;
  updated_at: string;
  workspace_id: string;
  descricao: string;
  cliente: string;
  numero_referencia?: string | null;
  data_emissao: string;
  data_vencimento: string;
  valor_liquido: number;
  valor_recebido: number;
  data_recebimento?: string | null;
  observacao?: string | null;
  include_in_dashboard?: boolean;
  status: ReceivableViewStatus;
}

export async function createReceivableManualItem(payload: {
  descricao: string;
  cliente: string;
  numero_referencia?: string | null;
  data_emissao: string;
  data_vencimento: string;
  valor_liquido: number;
  valor_recebido?: number | null;
  data_recebimento?: string | null;
  observacao?: string | null;
  include_in_dashboard?: boolean;
}): Promise<ReceivableManualItem> {
  const { data } = await api.post<ReceivableManualItem>("/financial/receivables/manual", payload);
  return data;
}

export async function updateReceivableManualItem(
  id: string,
  payload: Partial<{
    descricao: string;
    cliente: string;
    numero_referencia: string | null;
    data_emissao: string;
    data_vencimento: string;
    valor_liquido: number;
    valor_recebido: number | null;
    data_recebimento: string | null;
    observacao: string | null;
    include_in_dashboard: boolean;
  }>,
): Promise<ReceivableManualItem> {
  const { data } = await api.patch<ReceivableManualItem>(`/financial/receivables/manual/${id}`, payload);
  return data;
}

export async function deleteReceivableManualItem(id: string): Promise<void> {
  await api.delete(`/financial/receivables/manual/${id}`);
}

export async function createReceivableInvoice(payload: {
  project_id: string;
  number: string;
  issue_date: string;
  due_days: 30 | 60 | 90;
  gross_amount: number;
  net_amount?: number | null;
  client_name?: string | null;
  notes?: string | null;
  include_in_dashboard?: boolean;
}): Promise<ReceivableInvoice> {
  const { data } = await api.post<ReceivableInvoice>("/invoices/", payload);
  return data;
}

export async function reactivateReceivableInvoice(id: string): Promise<ReceivableInvoice> {
  const { data } = await api.post<ReceivableInvoice>(`/invoices/${id}/reactivate/`);
  return data;
}

export async function updateReceivableInvoice(
  id: string,
  payload: Partial<{
    number: string;
    issue_date: string;
    due_days: 30 | 60 | 90;
    gross_amount: number;
    net_amount: number;
    client_name: string | null;
    notes: string | null;
    is_anticipated: boolean;
    institution: string | null;
    advance_amount_received: number | null;
    advance_amount_due: number | null;
    advance_due_date: string | null;
    received_amount: number;
    received_date: string | null;
    status: InvoiceStatus;
    include_in_dashboard: boolean;
  }>,
): Promise<ReceivableInvoice> {
  const { data } = await api.patch<ReceivableInvoice>(`/invoices/${id}/`, payload);
  return data;
}

export async function addInvoiceAnticipation(
  invoiceId: string,
  payload: {
    institution: string;
    amount_received: number;
    amount_to_repay: number;
    data_recebimento: string;
    due_date: string;
    include_in_dashboard?: boolean;
  },
): Promise<InvoiceAnticipation> {
  const { data } = await api.post<InvoiceAnticipation>(`/invoices/${invoiceId}/anticipations/`, payload);
  return data;
}

export async function deleteInvoiceAnticipation(invoiceId: string, anticipationId: string): Promise<void> {
  await api.delete(`/invoices/${invoiceId}/anticipations/${anticipationId}/`);
}

export async function updateInvoiceAnticipation(
  invoiceId: string,
  anticipationId: string,
  payload: {
    institution: string;
    amount_received: number;
    amount_to_repay: number;
    data_recebimento: string;
    due_date: string;
    include_in_dashboard?: boolean;
  },
): Promise<InvoiceAnticipation> {
  const { data } = await api.patch<InvoiceAnticipation>(
    `/invoices/${invoiceId}/anticipations/${anticipationId}/`,
    {
      institution: payload.institution,
      amount_received: payload.amount_received,
      amount_to_repay: payload.amount_to_repay,
      data_recebimento: payload.data_recebimento,
      repayment_date: payload.due_date,
    },
  );
  return data;
}


export async function deleteReceivableInvoice(id: string): Promise<void> {
  await api.delete(`/invoices/${id}/`);
}

export async function uploadInvoicePdf(invoiceId: string, file: File): Promise<ReceivableInvoice> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<ReceivableInvoice>(`/invoices/${invoiceId}/pdf/`, form);
  return data;
}

export async function deleteInvoicePdf(invoiceId: string): Promise<ReceivableInvoice> {
  const { data } = await api.delete<ReceivableInvoice>(`/invoices/${invoiceId}/pdf/`);
  return data;
}

export async function downloadInvoicePdfBlob(invoiceId: string): Promise<Blob> {
  const { data } = await api.get<Blob>(`/invoices/${invoiceId}/pdf/`, { responseType: "blob" });
  return data;
}

export function openPdfBlobInNewTab(blob: Blob): void {
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener,noreferrer");
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
