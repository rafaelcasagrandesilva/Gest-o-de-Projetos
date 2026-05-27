import type { InvoiceStatus, ReceivableInvoice } from "@/services/receivables";
import { compareDateIso, compareText } from "@/utils/sortComparators";
import type { SortColumnDef } from "@/utils/sortTableRows";

export type InvoiceSortColumn =
  | "project"
  | "number"
  | "issue_date"
  | "due_days"
  | "due_date"
  | "gross_amount"
  | "net_amount"
  | "received_amount"
  | "status";

const INVOICE_STATUS_ORDER: Record<InvoiceStatus, number> = {
  EMITIDA: 1,
  ANTECIPADA: 2,
  RECEBIDA: 3,
  CANCELADA: 4,
};

export const INVOICE_SORT_COLUMNS: Record<InvoiceSortColumn, SortColumnDef<ReceivableInvoice>> = {
  project: { kind: "text", getValue: (r) => r.project_name ?? "" },
  number: { kind: "documentNumber", getValue: (r) => r.number },
  issue_date: { kind: "date", getValue: (r) => r.issue_date },
  due_days: { kind: "number", getValue: (r) => r.due_days },
  due_date: { kind: "date", getValue: (r) => r.due_date },
  gross_amount: { kind: "money", getValue: (r) => r.gross_amount },
  net_amount: { kind: "money", getValue: (r) => r.net_amount },
  received_amount: { kind: "money", getValue: (r) => r.received_amount },
  status: { kind: "status", getValue: (r) => r.status, statusOrder: INVOICE_STATUS_ORDER },
};

export function defaultInvoiceSort(a: ReceivableInvoice, b: ReceivableInvoice): number {
  const byDue = compareDateIso(a.due_date, b.due_date);
  if (byDue !== 0) return byDue;
  return compareText(a.number, b.number);
}
