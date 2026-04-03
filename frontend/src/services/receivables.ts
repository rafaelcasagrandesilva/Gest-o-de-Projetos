import { api } from "./api";

export type NfStatus = "PAGA" | "PENDENTE" | "ATRASADA";

export interface ReceivableInvoice {
  id: string;
  project_id: string;
  project_name: string | null;
  numero_nf: string;
  data_emissao: string;
  valor_bruto: number;
  vencimento: string;
  data_prevista_pagamento: string | null;
  numero_pedido: string | null;
  numero_conformidade: string | null;
  observacao: string | null;
  antecipada: boolean;
  instituicao: string | null;
  taxa_juros_mensal: number | null;
  total_recebido: number;
  saldo: number;
  status: NfStatus;
}

export interface ReceivablePayment {
  id: string;
  invoice_id: string;
  data_recebimento: string;
  valor: number;
  created_at: string;
  updated_at: string;
}

export interface ReceivableKpis {
  total_a_receber: number;
  recebido_no_mes: number;
  em_atraso_valor: number;
  total_nfs: number;
}

export async function fetchReceivableInvoices(params: {
  project_id?: string;
  status?: NfStatus;
  year?: number;
  month?: number;
}): Promise<ReceivableInvoice[]> {
  const { data } = await api.get<ReceivableInvoice[]>("/invoices", { params });
  return data;
}

export async function fetchReceivableKpis(params: {
  project_id?: string;
  year?: number;
  month?: number;
}): Promise<ReceivableKpis> {
  const { data } = await api.get<ReceivableKpis>("/invoices/kpis", { params });
  return data;
}

export async function createReceivableInvoice(payload: {
  project_id: string;
  numero_nf: string;
  data_emissao: string;
  valor_bruto: number;
  vencimento: string;
  data_prevista_pagamento?: string | null;
  numero_pedido?: string | null;
  numero_conformidade?: string | null;
  observacao?: string | null;
  antecipada?: boolean;
  instituicao?: string | null;
  taxa_juros_mensal?: number | null;
}): Promise<ReceivableInvoice> {
  const { data } = await api.post<ReceivableInvoice>("/invoices", payload);
  return data;
}

export async function deleteReceivableInvoice(id: string): Promise<void> {
  await api.delete(`/invoices/${id}`);
}

export async function fetchInvoicePayments(invoiceId: string): Promise<ReceivablePayment[]> {
  const { data } = await api.get<ReceivablePayment[]>(`/invoices/${invoiceId}/payments`);
  return data;
}

export async function addInvoicePayment(
  invoiceId: string,
  payload: { data_recebimento: string; valor: number },
): Promise<ReceivablePayment> {
  const { data } = await api.post<ReceivablePayment>(`/invoices/${invoiceId}/payments`, payload);
  return data;
}

export async function deleteInvoicePayment(paymentId: string): Promise<void> {
  await api.delete(`/payments/${paymentId}`);
}
