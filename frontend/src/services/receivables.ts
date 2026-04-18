import { api } from "./api";

export type InvoiceStatus = "EMITIDA" | "ANTECIPADA" | "FINALIZADA" | "CANCELADA";

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
  received_amount: number;
  received_date: string | null;
  interest_amount: number;
  implied_monthly_rate_percent: number | null;
  status: InvoiceStatus;
  has_pdf: boolean;
  pdf_url: string | null;
  activity_log: string | null;
}

export interface ReceivableKpis {
  total_a_receber: number;
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

export async function createReceivableInvoice(payload: {
  project_id: string;
  number: string;
  issue_date: string;
  due_days: 30 | 60 | 90;
  gross_amount: number;
  net_amount?: number | null;
  client_name?: string | null;
  notes?: string | null;
}): Promise<ReceivableInvoice> {
  const { data } = await api.post<ReceivableInvoice>("/invoices/", payload);
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
    received_amount: number;
    received_date: string | null;
    status: InvoiceStatus;
  }>,
): Promise<ReceivableInvoice> {
  const { data } = await api.patch<ReceivableInvoice>(`/invoices/${id}/`, payload);
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
