import type { PayableSnapshotRow, PayableSnapshotStatus } from "@/services/payables";
import { compareDateIso, compareText } from "@/utils/sortComparators";
import type { SortColumnDef } from "@/utils/sortTableRows";

export type PayableSortColumn =
  | "type"
  | "name"
  | "month"
  | "cost_center"
  | "amount_original"
  | "amount_final"
  | "amount_paid"
  | "amount_remaining"
  | "due_date"
  | "status"
  | "last_payment";

const PAYABLE_STATUS_ORDER: Record<PayableSnapshotStatus, number> = {
  ABERTO: 1,
  PARCIAL: 2,
  PAGO: 3,
};

export function payableTypeLabel(t: PayableSnapshotRow["type"]): string {
  if (t === "COLLABORATOR") return "Colaborador";
  if (t === "VEHICLE") return "Veículos";
  if (t === "FIXED_COST") return "Custo diverso";
  if (t === "ENDIVIDAMENTO" || t === "FINANCIAL") return "Endividamento";
  if (t === "ANTECIPACAO") return "Antecipação";
  if (t === "MANUAL") return "Manual";
  return t;
}

export const PAYABLE_SORT_COLUMNS: Record<PayableSortColumn, SortColumnDef<PayableSnapshotRow>> = {
  type: { kind: "text", getValue: (r) => payableTypeLabel(r.type) },
  name: { kind: "text", getValue: (r) => r.name },
  month: { kind: "date", getValue: (r) => r.month },
  cost_center: { kind: "text", getValue: (r) => r.cost_center },
  amount_original: { kind: "money", getValue: (r) => r.amount_original },
  amount_final: { kind: "money", getValue: (r) => r.amount_final },
  amount_paid: { kind: "money", getValue: (r) => r.amount_paid },
  amount_remaining: { kind: "money", getValue: (r) => r.amount_remaining },
  due_date: { kind: "date", getValue: (r) => r.due_date },
  status: { kind: "status", getValue: (r) => r.status, statusOrder: PAYABLE_STATUS_ORDER },
  last_payment: { kind: "date", getValue: (r) => r.last_payment_date ?? "" },
};

export function defaultPayableSort(a: PayableSnapshotRow, b: PayableSnapshotRow): number {
  const byDue = compareDateIso(a.due_date, b.due_date);
  if (byDue !== 0) return byDue;
  return compareText(a.name, b.name);
}

function isPayableRowPaidInView(r: PayableSnapshotRow): boolean {
  if (r.status === "PAGO") return true;
  return Number(r.paid_in_period ?? 0) > 0.005;
}

/** Listagem operacional: abertos primeiro, depois pagos no período; vencimento ↑; pagos por último pagamento ↓. */
export function defaultPayableOperationalSort(a: PayableSnapshotRow, b: PayableSnapshotRow): number {
  const aPaid = isPayableRowPaidInView(a);
  const bPaid = isPayableRowPaidInView(b);
  if (aPaid !== bPaid) return aPaid ? 1 : -1;

  if (!aPaid) {
    const byDue = compareDateIso(a.due_date, b.due_date);
    if (byDue !== 0) return byDue;
    return compareText(a.name, b.name);
  }

  const byPay = compareDateIso(b.last_payment_date ?? "", a.last_payment_date ?? "");
  if (byPay !== 0) return byPay;
  return compareText(a.name, b.name);
}
