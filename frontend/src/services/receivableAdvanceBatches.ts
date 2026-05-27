import { api } from "./api";

export type AdvanceBatchStatus = "OPEN" | "SETTLED" | "CANCELLED";

export interface AdvanceBatchSummary {
  id: string;
  batch_number: string;
  institution: string;
  status: AdvanceBatchStatus;
}

export interface AdvanceBatchEligibleInvoice {
  id: string;
  project_id: string;
  project_name: string | null;
  number: string;
  client_name: string | null;
  issue_date: string;
  due_date: string;
  gross_amount: number;
  net_amount: number;
  status: string;
}

export interface AdvanceBatchItem {
  id: string;
  batch_id: string;
  invoice_id: string;
  invoice_amount: number;
  invoice_number: string | null;
  client_name: string | null;
  project_name: string | null;
  issue_date: string | null;
  due_date: string | null;
}

export interface AdvanceBatch {
  id: string;
  batch_number: string;
  operation_type?: "BORDERO" | "FACTORING" | "FIDC" | "OUTROS";
  operation_code?: string | null;
  institution: string;
  gross_amount: number;
  received_amount: number;
  discount_amount: number;
  fee_amount: number;
  receive_date: string;
  repayment_date: string;
  observation: string | null;
  status: AdvanceBatchStatus;
  created_by_id: string | null;
  items: AdvanceBatchItem[];
  invoice_count: number;
  discount_percent: number | null;
  created_at: string;
  updated_at: string;
}

export async function fetchEligibleInvoicesForBatch(params?: {
  search?: string;
  project_id?: string;
}): Promise<AdvanceBatchEligibleInvoice[]> {
  const { data } = await api.get<AdvanceBatchEligibleInvoice[]>("/invoices/advance-batches/eligible-invoices", {
    params,
  });
  return data;
}

export async function createAdvanceBatch(payload: {
  operation_type?: "BORDERO" | "FACTORING" | "FIDC" | "OUTROS";
  operation_code?: string | null;
  institution: string;
  received_amount: number;
  discount_amount: number;
  fee_amount: number;
  receive_date: string;
  repayment_date: string;
  observation?: string | null;
  invoice_ids: string[];
}): Promise<AdvanceBatch> {
  const { data } = await api.post<AdvanceBatch>("/invoices/advance-batches", payload);
  return data;
}

export async function fetchAdvanceBatch(batchId: string): Promise<AdvanceBatch> {
  const { data } = await api.get<AdvanceBatch>(`/invoices/advance-batches/${batchId}`);
  return data;
}

export async function fetchAdvanceBatches(): Promise<AdvanceBatch[]> {
  const { data } = await api.get<AdvanceBatch[]>("/invoices/advance-batches");
  return data;
}

export async function cancelAdvanceBatch(batchId: string): Promise<void> {
  await api.delete(`/invoices/advance-batches/${batchId}`);
}

export async function deleteAdvanceBatchHard(batchId: string): Promise<void> {
  await api.delete(`/invoices/advance-batches/${batchId}/hard`);
}
