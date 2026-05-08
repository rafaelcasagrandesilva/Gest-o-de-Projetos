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

export type PayableSnapshotType = "COLLABORATOR" | "VEHICLE" | "FIXED_COST" | "FINANCIAL" | "ANTECIPACAO" | "MANUAL";

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

  due_date: string;
  payment_date: string | null;
  paid: boolean;

  observation: string | null;
  status: PayableSnapshotStatus;
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
  payload: Partial<{ amount_final: number; due_date: string; observation: string | null }>,
): Promise<PayableSnapshotRow> {
  const { data } = await api.patch<PayableSnapshotRow>(`/financial/payables/${id}/`, payload);
  return data;
}

export async function registerPayablePayment(
  id: string,
  payload: { amount: number; observation?: string | null },
): Promise<PayableSnapshotRow> {
  const { data } = await api.post<PayableSnapshotRow>(`/financial/payables/${id}/register-payment/`, payload);
  return data;
}

export async function reversePayablePayment(
  id: string,
  payload: { amount: number; observation?: string | null },
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
