import type { MonthlyPoint } from "@/services/dashboard";

/** Campos mínimos para custo total do dashboard operacional (projetos). */
export type CostTotalInput = Pick<
  MonthlyPoint,
  | "total_cost"
  | "cost_total"
  | "operational_cost"
  | "tax_amount"
  | "overhead_amount"
  | "anticipation_amount"
>;

/**
 * Custo total (realizado) — igual ao card KPI e ao backend (`FinancialService`):
 * operacional + impostos + rateio/overhead + antecipação.
 * Não inclui retenção.
 */
export function chartCostTotal(p: CostTotalInput): number {
  const fromApi = Number(p.total_cost ?? p.cost_total ?? 0);
  if (fromApi > 0) return fromApi;

  const fromComponents =
    Number(p.operational_cost ?? 0) +
    Number(p.tax_amount ?? 0) +
    Number(p.overhead_amount ?? 0) +
    Number(p.anticipation_amount ?? 0);
  return fromComponents > 0 ? fromComponents : 0;
}

/** Lucro operacional = receita − custo total (sem retenção). */
export function chartOperationalProfit(receita: number, custo: number, p: Pick<MonthlyPoint, "operational_profit" | "profit">): number {
  const fromApi = Number(p.operational_profit ?? p.profit ?? NaN);
  if (Number.isFinite(fromApi)) return fromApi;
  return receita - custo;
}

/** Lucro líquido = lucro operacional − retenção. */
export function chartNetProfit(
  operational: number,
  p: Pick<MonthlyPoint, "net_profit" | "profit" | "total_retention">,
): number {
  const fromApi = Number(p.net_profit ?? NaN);
  if (Number.isFinite(fromApi)) return fromApi;
  return operational - Number(p.total_retention ?? 0);
}
