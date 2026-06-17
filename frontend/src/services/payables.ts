import { api } from "./api";

/** Formata uma `Date` local como `YYYY-MM` (competência do mês). */
export function formatMonthToYYYYMM(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  return `${year}-${month}`;
}

/**
 * Normaliza o query param `month` da API GET `/financial/payables/`.
 * A API aceita apenas `YYYY-MM` (não use `YYYY-MM-DD` no GET).
 */
export function normalizePayablesMonthQuery(value: string): string {
  const s = value.trim();
  const m = /^(\d{4})-(\d{2})(?:-(\d{2}))?$/.exec(s);
  if (!m) {
    throw new Error(`month inválido: "${value}". Use YYYY-MM.`);
  }
  return `${m[1]}-${m[2]}`;
}

/** Primeiro dia do mês (`YYYY-MM-01`) para payloads que exigem data completa (ex.: POST manual). */
export function payablesMonthToCompetenceIsoDate(ymOrIso: string): string {
  return `${normalizePayablesMonthQuery(ymOrIso)}-01`;
}

export type PayableSnapshotStatus = "ABERTO" | "PARCIAL" | "PAGO";

export type PayableSnapshotType =
  | "COLLABORATOR"
  | "VEHICLE"
  | "FIXED_COST"
  | "ENDIVIDAMENTO"
  | "FINANCIAL"
  | "ANTECIPACAO"
  | "MANUAL";

export interface PayableSnapshotRow {
  id: string;
  created_at: string;
  updated_at: string;

  month: string;
  type: PayableSnapshotType;
  ref_id: string | null;
  project_id: string | null;

  name: string;
  cost_center: string;
  category: string;

  amount_original: number;
  amount_final: number;
  amount_paid: number;
  amount_remaining: number;
  is_overpaid: boolean;
  overpaid_amount: number;

  due_date: string;
  payment_date: string | null;
  paid: boolean;

  observation: string | null;
  include_in_dashboard: boolean;
  /** Reconciliação: lançamento automático cuja origem foi removida (resíduo). */
  is_obsolete: boolean;
  obsolete_reason: string | null;
  reconciled_at: string | null;
  status: PayableSnapshotStatus;
  /** Data do último pagamento ativo (evento de caixa). */
  last_payment_date: string | null;
  /** Soma dos pagamentos com data no mês filtrado (visão operacional). */
  paid_in_period?: number;
  competence_out_of_view?: boolean;
}

export async function listPayableSnapshots(params?: {
  month?: string | Date | null;
  /** Apaga e recria o snapshot do mês no servidor (use com cuidado: afeta todo o mês). */
  forceRegenerate?: boolean;
}): Promise<PayableSnapshotRow[]> {
  if (!params || params.month == null || (typeof params.month === "string" && params.month.trim() === "")) {
    const { data } = await api.get<PayableSnapshotRow[]>("/financial/payables/");
    return data;
  }
  const month =
    typeof params.month === "string" ? normalizePayablesMonthQuery(params.month) : formatMonthToYYYYMM(params.month);
  const { data } = await api.get<PayableSnapshotRow[]>("/financial/payables/", {
    params: {
      month,
      ...(params.forceRegenerate ? { force_regenerate: true } : {}),
    },
  });
  return data;
}

export async function updatePayableSnapshot(
  id: string,
  payload: Partial<{
    amount_final: number;
    due_date: string;
    observation: string | null;
    include_in_dashboard: boolean;
  }>,
): Promise<PayableSnapshotRow> {
  const { data } = await api.patch<PayableSnapshotRow>(`/financial/payables/${id}/`, payload);
  return data;
}

export async function registerPayablePayment(
  id: string,
  payload: {
    amount: number;
    payment_date?: string;
    observation?: string | null;
    allow_overpayment?: boolean;
  },
): Promise<PayableSnapshotRow> {
  const { data } = await api.post<PayableSnapshotRow>(`/financial/payables/${id}/register-payment/`, payload);
  return data;
}

export async function reversePayablePayment(
  id: string,
  payload: { amount: number; reversal_reason?: string | null; observation?: string | null },
): Promise<PayableSnapshotRow> {
  const { data } = await api.post<PayableSnapshotRow>(`/financial/payables/${id}/reverse-payment/`, payload);
  return data;
}

export async function createManualPayableSnapshot(payload: {
  month: string; // YYYY-MM ou YYYY-MM-01
  name: string;
  amount: number;
  due_date: string;
  category: string;
  cost_center: string;
  include_in_dashboard?: boolean;
}): Promise<PayableSnapshotRow> {
  const body = {
    ...payload,
    month: payablesMonthToCompetenceIsoDate(payload.month),
  };
  const { data } = await api.post<PayableSnapshotRow>("/financial/payables/", body);
  return data;
}

export async function deletePayableSnapshot(id: string): Promise<void> {
  await api.delete(`/financial/payables/${id}/`);
}

export interface PayableReconcileResult {
  month: string;
  checked: number;
  marked_obsolete: number;
  cleared: number;
  obsolete_total: number;
}

/** Reconcilia o snapshot do mês: marca obsoletos os automáticos sem origem atual. */
export async function reconcilePayableSnapshot(month: string | Date): Promise<PayableReconcileResult> {
  const m = typeof month === "string" ? normalizePayablesMonthQuery(month) : formatMonthToYYYYMM(month);
  const { data } = await api.post<PayableReconcileResult>("/financial/payables/reconcile", null, {
    params: { month: m },
  });
  return data;
}

export type PayableImportRowStatus = "valid" | "duplicate" | "error" | "empty";

export interface PayableImportPreviewRow {
  line_number: number;
  original_name: string | null;
  original_cost_center: string | null;
  original_due_date: string | null;
  original_amount: string | null;
  original_category: string | null;
  original_observation: string | null;

  cost_center: string | null;
  alias_applied: boolean;
  name: string | null;
  due_date: string | null;
  amount: number | null;
  observation: string | null;
  category: string | null;
  payment_month: string | null;
  status: PayableImportRowStatus;
  message: string | null;
}

export interface PayableImportPreviewResult {
  total_rows: number;
  valid_count: number;
  duplicate_count: number;
  error_count: number;
  empty_count: number;
  rows: PayableImportPreviewRow[];
}

export interface PayableImportConfirmResult {
  imported: number;
  skipped_duplicate: number;
  skipped_empty: number;
  errors: number;
  error_details: string[];
}

export interface PayableImportColumnMapping {
  name: string | null;
  cost_center: string | null;
  due_date: string | null;
  amount: string | null;
  category?: string | null;
  observation?: string | null;
}

export interface PayableImportCostCenterScanResult {
  unknown_centers: string[];
  available_targets: string[];
}

export interface CostCenterAlias {
  id: string;
  alias_name: string;
  target_cost_center: string;
  created_by_user_id: string | null;
  created_at: string;
}

export interface PayableImportAnalyzeResult {
  header_row: number;
  columns: string[];
  sample_rows: Record<string, unknown>[];
  suggested_mapping: PayableImportColumnMapping;
  detected_legacy_template: boolean;
  total_data_rows: number;
}

export interface PayableImportTemplate {
  id: string;
  name: string;
  header_row: number;
  column_mapping: PayableImportColumnMapping;
  created_at: string;
  updated_at: string;
}

function payablesImportFormData(
  file: File,
  fields?: Record<string, string | number>,
): FormData {
  const form = new FormData();
  form.append("file", file);
  if (fields) {
    for (const [key, value] of Object.entries(fields)) {
      form.append(key, String(value));
    }
  }
  return form;
}

export async function analyzePayablesImport(
  file: File,
  headerRow: number,
): Promise<PayableImportAnalyzeResult> {
  const { data } = await api.post<PayableImportAnalyzeResult>(
    "/financial/payables/import/analyze",
    payablesImportFormData(file, { header_row: headerRow }),
    { timeout: 120_000 },
  );
  return data;
}

export async function scanPayablesImportCostCenters(
  file: File,
  headerRow: number,
  mapping: PayableImportColumnMapping,
): Promise<PayableImportCostCenterScanResult> {
  const { data } = await api.post<PayableImportCostCenterScanResult>(
    "/financial/payables/import/mapped/scan-cost-centers",
    payablesImportFormData(file, {
      header_row: headerRow,
      mapping: JSON.stringify(mapping),
    }),
    { timeout: 120_000 },
  );
  return data;
}

export async function listCostCenterAliases(): Promise<CostCenterAlias[]> {
  const { data } = await api.get<CostCenterAlias[]>("/financial/cost-center-aliases");
  return data;
}

export async function createCostCenterAlias(payload: {
  alias_name: string;
  target_cost_center: string;
}): Promise<CostCenterAlias> {
  const { data } = await api.post<CostCenterAlias>("/financial/cost-center-aliases", payload);
  return data;
}

export async function deleteCostCenterAlias(aliasId: string): Promise<void> {
  await api.delete(`/financial/cost-center-aliases/${aliasId}`);
}

export async function previewPayablesImportMapped(
  file: File,
  headerRow: number,
  mapping: PayableImportColumnMapping,
  costCenterResolutions?: Record<string, string>,
): Promise<PayableImportPreviewResult> {
  const fields: Record<string, string | number> = {
    header_row: headerRow,
    mapping: JSON.stringify(mapping),
  };
  if (costCenterResolutions && Object.keys(costCenterResolutions).length > 0) {
    fields.cost_center_resolutions = JSON.stringify(costCenterResolutions);
  }
  const { data } = await api.post<PayableImportPreviewResult>(
    "/financial/payables/import/mapped/preview",
    payablesImportFormData(file, fields),
    { timeout: 120_000 },
  );
  return data;
}

export async function confirmPayablesImportMapped(
  file: File,
  headerRow: number,
  mapping: PayableImportColumnMapping,
  costCenterResolutions?: Record<string, string>,
): Promise<PayableImportConfirmResult> {
  const fields: Record<string, string | number> = {
    header_row: headerRow,
    mapping: JSON.stringify(mapping),
  };
  if (costCenterResolutions && Object.keys(costCenterResolutions).length > 0) {
    fields.cost_center_resolutions = JSON.stringify(costCenterResolutions);
  }
  const { data } = await api.post<PayableImportConfirmResult>(
    "/financial/payables/import/mapped/confirm",
    payablesImportFormData(file, fields),
    { timeout: 120_000 },
  );
  return data;
}

export async function listPayablesImportTemplates(): Promise<PayableImportTemplate[]> {
  const { data } = await api.get<PayableImportTemplate[]>("/financial/payables/import/templates");
  return data;
}

export async function createPayablesImportTemplate(payload: {
  name: string;
  header_row: number;
  column_mapping: PayableImportColumnMapping;
}): Promise<PayableImportTemplate> {
  const { data } = await api.post<PayableImportTemplate>("/financial/payables/import/templates", payload);
  return data;
}

export async function deletePayablesImportTemplate(templateId: string): Promise<void> {
  await api.delete(`/financial/payables/import/templates/${templateId}`);
}

/** Importação rápida — colunas fixas A–F (retrocompatível). */
export async function previewPayablesImportLegacy(file: File): Promise<PayableImportPreviewResult> {
  const { data } = await api.post<PayableImportPreviewResult>(
    "/financial/payables/import/preview",
    payablesImportFormData(file),
    { timeout: 120_000 },
  );
  return data;
}

export async function confirmPayablesImportLegacy(file: File): Promise<PayableImportConfirmResult> {
  const { data } = await api.post<PayableImportConfirmResult>(
    "/financial/payables/import/confirm",
    payablesImportFormData(file),
    { timeout: 120_000 },
  );
  return data;
}
