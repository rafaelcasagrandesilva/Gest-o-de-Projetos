import { hydrateBlobError } from "@/utils/apiError";
import { saveBlobAsFile, viewFileInNewTab } from "@/utils/fileView";
import { api } from "./api";

export type AdvanceBatchStatus = "DRAFT" | "OPEN" | "SETTLED" | "CANCELLED";

export interface AdvanceBatchSummary {
  id: string;
  sgc_number: number;
  batch_number: string;
  institution: string;
  status: AdvanceBatchStatus;
}

/** Resumo curto de uma operação para indicadores de histórico N:N (regras 4 e 6). */
export interface AdvanceOperationSummary {
  id: string;
  sgc_number: number | null;
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
  /** Histórico N:N (regra 4): operações válidas em que a NF já participou. */
  operations_count?: number;
  operations?: AdvanceOperationSummary[];
}

export interface AdvanceBatchItem {
  id: string;
  batch_id: string;
  invoice_id: string;
  invoice_amount: number;
  advance_basis?: string | null;
  advanced_amount?: number | null;
  invoice_number: string | null;
  client_name: string | null;
  project_name: string | null;
  competence_month?: string | null;
  gross_amount?: number | null;
  net_amount?: number | null;
  issue_date: string | null;
  due_date: string | null;
  invoice_status?: string | null;
  /** Regra 6: outras operações válidas em que esta mesma NF participa. */
  other_operations?: AdvanceOperationSummary[];
}

export interface AdvanceBatch {
  id: string;
  sgc_number: number;
  batch_number: string;
  operation_type?: "BORDERO" | "FACTORING" | "FIDC" | "OUTROS";
  operation_code?: string | null;
  institution: string;
  institution_id?: string | null;
  institution_profile?: string | null;
  gross_amount: number;
  received_amount: number;
  expected_amount?: number | null;
  actual_received_amount?: number | null;
  discount_amount: number;
  fee_amount: number;
  repasse_enabled?: boolean;
  repasse_amount?: number | null;
  receive_date: string;
  repayment_date: string;
  confirmed_at?: string | null;
  observation: string | null;
  include_in_dashboard: boolean;
  status: AdvanceBatchStatus;
  created_by_id: string | null;
  items: AdvanceBatchItem[];
  invoice_count: number;
  discount_percent: number | null;
  advanced_total?: number | null;
  finance_cost_amount?: number | null;
  finance_cost_percent?: number | null;
  /** Documentos anexados à operação (borderô/termo da instituição). */
  attachment_count?: number;
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

export type AdvanceBasis = "BRUTO" | "LIQUIDO" | "LIQUIDO_MENOS_10" | "MANUAL";

export interface AdvanceItemInput {
  invoice_id: string;
  advance_basis?: AdvanceBasis | null;
  advanced_amount?: number | null;
}

export async function createAdvanceBatch(payload: {
  operation_type?: "BORDERO" | "FACTORING" | "FIDC" | "OUTROS";
  operation_code?: string | null;
  institution_id: string;
  received_amount?: number;
  discount_amount?: number;
  fee_amount?: number;
  repasse_enabled?: boolean;
  receive_date: string;
  /** Opcional: perfis sem devolução (ex.: Daycoval) não a informam. */
  repayment_date?: string | null;
  observation?: string | null;
  invoice_ids?: string[];
  items?: AdvanceItemInput[];
}): Promise<AdvanceBatch> {
  const { data } = await api.post<AdvanceBatch>("/invoices/advance-batches", payload);
  return data;
}

/** Edita uma operação ATIVA (reverte → aplica novos dados → reaplica). Mesmo payload da criação.
 * Bloqueado no backend quando há pagamento nas despesas do borderô (só resta cancelar). */
export async function editAdvanceBatch(
  batchId: string,
  payload: {
    operation_type?: "BORDERO" | "FACTORING" | "FIDC" | "OUTROS";
    operation_code?: string | null;
    institution_id: string;
    received_amount?: number;
    discount_amount?: number;
    fee_amount?: number;
    repasse_enabled?: boolean;
    receive_date: string;
    repayment_date?: string | null;
    observation?: string | null;
    invoice_ids?: string[];
    items?: AdvanceItemInput[];
  },
): Promise<AdvanceBatch> {
  const { data } = await api.put<AdvanceBatch>(`/invoices/advance-batches/${batchId}`, payload);
  return data;
}

export async function updateAdvanceBatchDashboardInclusion(
  batchId: string,
  include_in_dashboard: boolean,
): Promise<AdvanceBatch> {
  const { data } = await api.patch<AdvanceBatch>(`/invoices/advance-batches/${batchId}`, {
    include_in_dashboard,
  });
  return data;
}

/** Informa o valor efetivamente recebido (realizado) — perfis com previsto×realizado (Daycoval). */
export async function setAdvanceBatchActualReceived(
  batchId: string,
  actual_received_amount: number,
): Promise<AdvanceBatch> {
  const { data } = await api.patch<AdvanceBatch>(`/invoices/advance-batches/${batchId}`, {
    actual_received_amount,
  });
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

export async function confirmAdvanceBatch(batchId: string): Promise<AdvanceBatch> {
  const { data } = await api.post<AdvanceBatch>(`/invoices/advance-batches/${batchId}/confirm`);
  return data;
}

export async function cancelAdvanceBatch(batchId: string): Promise<void> {
  await api.delete(`/invoices/advance-batches/${batchId}`);
}

export async function deleteAdvanceBatchHard(batchId: string): Promise<void> {
  await api.delete(`/invoices/advance-batches/${batchId}/hard`);
}

/** Documento anexado à operação (borderô/termo da instituição). */
export interface AdvanceBatchAttachment {
  id: string;
  batch_id: string;
  file_name: string;
  mime_type: string | null;
  size_bytes: number;
  created_at: string;
  download_url: string;
}

export async function listAdvanceBatchAttachments(batchId: string): Promise<AdvanceBatchAttachment[]> {
  const { data } = await api.get<AdvanceBatchAttachment[]>(`/invoices/advance-batches/${batchId}/attachments`);
  return data;
}

/** Envia o lote numa requisição (o backend recusa tudo se um arquivo for inválido). */
export async function uploadAdvanceBatchAttachments(batchId: string, files: File[]): Promise<AdvanceBatchAttachment[]> {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  const { data } = await api.post<AdvanceBatchAttachment[]>(`/invoices/advance-batches/${batchId}/attachments`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function deleteAdvanceBatchAttachment(batchId: string, attachmentId: string): Promise<void> {
  await api.delete(`/invoices/advance-batches/${batchId}/attachments/${attachmentId}`);
}

async function fetchAdvanceBatchAttachmentBlob(att: AdvanceBatchAttachment): Promise<Blob> {
  try {
    const resp = await api.get<Blob>(`/${att.download_url}`, { responseType: "blob" });
    return resp.data;
  } catch (e) {
    throw await hydrateBlobError(e);
  }
}

export async function viewAdvanceBatchAttachment(att: AdvanceBatchAttachment): Promise<void> {
  await viewFileInNewTab(() => fetchAdvanceBatchAttachmentBlob(att));
}

export async function downloadAdvanceBatchAttachment(att: AdvanceBatchAttachment): Promise<void> {
  saveBlobAsFile(await fetchAdvanceBatchAttachmentBlob(att), att.file_name);
}
