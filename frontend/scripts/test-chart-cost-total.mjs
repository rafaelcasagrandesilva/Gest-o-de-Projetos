/**
 * Valida fórmula de custo total do gráfico Evolução Financeira (sem retenção).
 * Espelha frontend/src/utils/projectDashboardCost.ts
 */

function chartCostTotal(p) {
  const fromApi = Number(p.total_cost ?? p.cost_total ?? 0);
  if (fromApi > 0) return fromApi;
  const fromComponents =
    Number(p.operational_cost ?? 0) +
    Number(p.tax_amount ?? 0) +
    Number(p.overhead_amount ?? 0) +
    Number(p.anticipation_amount ?? 0);
  return fromComponents > 0 ? fromComponents : 0;
}

function chartOperationalProfit(receita, custo, p) {
  const fromApi = Number(p.operational_profit ?? p.profit ?? NaN);
  if (Number.isFinite(fromApi)) return fromApi;
  return receita - custo;
}

function chartNetProfit(operational, p) {
  const fromApi = Number(p.net_profit ?? NaN);
  if (Number.isFinite(fromApi)) return fromApi;
  return operational - Number(p.total_retention ?? 0);
}

const point = {
  total_revenue: 2_500_000,
  operational_cost: 1_386_902.04,
  tax_amount: 182_808.73,
  overhead_amount: 182_808.73,
  anticipation_amount: 182_808.73,
  total_retention: 50_000,
  total_cost: 1_935_328.23,
  operational_profit: 564_671.77,
  net_profit: 514_671.77,
};

const receita = point.total_revenue;
const custo = chartCostTotal(point);
const lucroOp = chartOperationalProfit(receita, custo, point);
const lucroLiq = chartNetProfit(lucroOp, point);

let failed = 0;

function assertClose(label, actual, expected, tol = 0.02) {
  if (Math.abs(actual - expected) > tol) {
    console.error(`FAIL ${label}: got ${actual}, expected ${expected}`);
    failed++;
  } else {
    console.log(`OK ${label}`);
  }
}

assertClose("custo total", custo, 1_935_328.23);
assertClose("custo sem retenção", custo, receita - lucroOp);
assertClose("lucro operacional", lucroOp, receita - custo);
assertClose("lucro líquido", lucroLiq, lucroOp - point.total_retention);
assertClose(
  "custo ≠ receita - lucro líquido (retenção fora do custo)",
  custo,
  receita - lucroLiq,
  50_000,
);

// Não somar retenção aos componentes
const wrongWithRetention =
  point.operational_cost +
  point.tax_amount +
  point.overhead_amount +
  point.anticipation_amount +
  point.total_retention;
if (Math.abs(custo - wrongWithRetention) < 1) {
  console.error("FAIL custo não deve incluir retenção");
  failed++;
} else {
  console.log("OK custo exclui retenção");
}

if (failed > 0) {
  process.exit(1);
}
console.log("All chart cost total checks passed.");
