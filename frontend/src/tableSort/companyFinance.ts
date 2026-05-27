import type { CompanyFinancialItem } from "@/services/companyFinance";
import { compareText } from "@/utils/sortComparators";
import type { SortColumnDef } from "@/utils/sortTableRows";

export type CompanyFinanceSortColumn =
  | "nome"
  | "category"
  | "cost_center"
  | "valor_referencia"
  | "total_pago"
  | "pago_mes"
  | "status";

const FINANCE_STATUS_ORDER: Record<string, number> = {
  ativo: 1,
  quitado: 2,
};

export const COMPANY_FINANCE_SORT_COLUMNS: Record<
  CompanyFinanceSortColumn,
  SortColumnDef<CompanyFinancialItem>
> = {
  nome: { kind: "text", getValue: (i) => i.nome },
  category: { kind: "text", getValue: (i) => i.category ?? "" },
  cost_center: { kind: "text", getValue: (i) => i.cost_center ?? "" },
  valor_referencia: { kind: "money", getValue: (i) => i.valor_referencia },
  total_pago: { kind: "money", getValue: (i) => i.total_pago },
  pago_mes: { kind: "money", getValue: (i) => i.pago_mes },
  status: {
    kind: "status",
    getValue: (i) => (i.status ?? "").toLowerCase(),
    statusOrder: FINANCE_STATUS_ORDER,
  },
};

export function defaultCompanyFinanceSort(a: CompanyFinancialItem, b: CompanyFinancialItem): number {
  return compareText(a.nome, b.nome);
}
