import type { AdvanceBatch, AdvanceBatchStatus } from "@/services/receivableAdvanceBatches";
import { compareDateIso } from "@/utils/sortComparators";
import type { SortColumnDef } from "@/utils/sortTableRows";

export type AdvanceBatchSortColumn =
  | "sgc"
  | "operation_code"
  | "institution"
  | "invoice_count"
  | "repasse"
  | "received"
  | "discount"
  | "fee"
  | "receive_date"
  | "status";

const STATUS_ORDER: Record<AdvanceBatchStatus, number> = {
  DRAFT: 0,
  OPEN: 1,
  SETTLED: 2,
  CANCELLED: 3,
};

export const ADVANCE_BATCH_SORT_COLUMNS: Record<AdvanceBatchSortColumn, SortColumnDef<AdvanceBatch>> = {
  sgc: { kind: "number", getValue: (b) => Number(b.sgc_number ?? 0) },
  operation_code: { kind: "documentNumber", getValue: (b) => b.operation_code ?? "" },
  institution: { kind: "text", getValue: (b) => b.institution ?? "" },
  invoice_count: { kind: "number", getValue: (b) => Number(b.invoice_count ?? 0) },
  repasse: { kind: "money", getValue: (b) => (b.repasse_enabled ? Number(b.repasse_amount ?? 0) : 0) },
  received: { kind: "money", getValue: (b) => Number(b.received_amount ?? 0) },
  discount: { kind: "money", getValue: (b) => Number(b.discount_amount ?? 0) },
  fee: { kind: "money", getValue: (b) => Number(b.fee_amount ?? 0) },
  receive_date: { kind: "date", getValue: (b) => b.receive_date ?? "" },
  status: { kind: "status", getValue: (b) => b.status, statusOrder: STATUS_ORDER },
};

/** Ordem padrão (sem coluna escolhida): recebimento mais recente primeiro. */
export function defaultAdvanceBatchSort(a: AdvanceBatch, b: AdvanceBatch): number {
  return compareDateIso(b.receive_date, a.receive_date);
}
