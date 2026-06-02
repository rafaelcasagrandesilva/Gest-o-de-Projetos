import type { ReceivableViewRow, ReceivableViewType } from "@/services/receivables";
import { compareDateIso, compareText } from "@/utils/sortComparators";
import type { SortColumnDef } from "@/utils/sortTableRows";

export type ReceivableUiStatus = "ABERTO" | "RECEBIDO" | "EM_ATRASO" | "CANCELADA";

export type ReceivableViewItem = {
  r: ReceivableViewRow;
  tipo: ReceivableViewType;
  net: number;
  recv: number;
  saldo: number;
  uiStatus: ReceivableUiStatus;
};

export type ReceivableViewSortColumn =
  | "tipo"
  | "client"
  | "number"
  | "issue_date"
  | "due_date"
  | "net"
  | "advance"
  | "customer"
  | "received_at"
  | "saldo"
  | "status";

const RECEIVABLE_UI_STATUS_ORDER: Record<ReceivableUiStatus, number> = {
  CANCELADA: 0,
  EM_ATRASO: 1,
  ABERTO: 2,
  RECEBIDO: 3,
};

export const RECEIVABLE_VIEW_SORT_COLUMNS: Record<
  ReceivableViewSortColumn,
  SortColumnDef<ReceivableViewItem>
> = {
  tipo: { kind: "text", getValue: (x) => x.tipo },
  client: { kind: "text", getValue: (x) => x.r.client ?? "" },
  number: { kind: "documentNumber", getValue: (x) => x.r.number },
  issue_date: { kind: "date", getValue: (x) => x.r.issue_date },
  due_date: { kind: "date", getValue: (x) => x.r.due_date },
  net: { kind: "money", getValue: (x) => x.net },
  advance: { kind: "money", getValue: (x) => Number(x.r.amount_received_advance ?? 0) },
  customer: { kind: "money", getValue: (x) => Number(x.r.amount_received_customer ?? 0) },
  received_at: { kind: "date", getValue: (x) => x.r.received_at ?? "" },
  saldo: { kind: "money", getValue: (x) => x.saldo },
  status: { kind: "status", getValue: (x) => x.uiStatus, statusOrder: RECEIVABLE_UI_STATUS_ORDER },
};

export function defaultReceivableViewSort(a: ReceivableViewItem, b: ReceivableViewItem): number {
  const byDue = compareDateIso(a.r.due_date, b.r.due_date);
  if (byDue !== 0) return byDue;
  return compareText(a.r.number, b.r.number);
}
