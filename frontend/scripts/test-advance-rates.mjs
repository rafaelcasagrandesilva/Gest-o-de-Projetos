/**
 * Valida a matemática dos cards de taxa da tela de Antecipações.
 * Espelha frontend/src/utils/advanceRates.ts (mesma convenção dos demais test-*.mjs:
 * o .mjs replica a fórmula porque não importa TypeScript direto).
 *
 * Os casos são os borderôs REAIS de junho/2026 (SGC 13 e 14, Lepta) e as duas cessões
 * do Banco Daycoval do mesmo mês, conferidos contra o banco e contra as cartas de cessão.
 *
 * Rodar: node scripts/test-advance-rates.mjs
 */

const DAY_MS = 86_400_000;
const CONFIRMED = new Set(["OPEN", "SETTLED"]);

function isoToUtc(iso) {
  if (!iso) return null;
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return null;
  return Date.UTC(y, m - 1, d);
}

function advancedAmountOf(b) {
  let sum = 0;
  let found = false;
  for (const item of b.items ?? []) {
    if (item.advanced_amount == null) continue;
    sum += Number(item.advanced_amount);
    found = true;
  }
  if (found) return sum;
  return Number(b.received_amount ?? 0) + Number(b.discount_amount ?? 0) + Number(b.fee_amount ?? 0);
}

function financeCostOf(b) {
  const cost = advancedAmountOf(b) - Number(b.received_amount ?? 0);
  return cost > 0 ? cost : 0;
}

const repasseOf = (b) => (b.repasse_enabled ? Number(b.repasse_amount ?? 0) : 0);

function weightedTermDays(b) {
  const start = isoToUtc(b.receive_date);
  if (start == null) return null;
  let weight = 0;
  let acc = 0;
  for (const item of b.items ?? []) {
    const due = isoToUtc(item.due_date);
    if (due == null) continue;
    const value = Number(item.advanced_amount ?? item.invoice_amount ?? 0);
    if (!(value > 0)) continue;
    weight += value;
    acc += value * ((due - start) / DAY_MS);
  }
  if (!(weight > 0)) return null;
  const days = acc / weight;
  return days > 0 ? days : null;
}

function monthlyRate(cost, advanced, termDays) {
  if (termDays == null || !(termDays > 0)) return null;
  const net = advanced - cost;
  if (!(net > 0) || !(cost > 0)) return null;
  return ((1 + cost / net) ** (30 / termDays) - 1) * 100;
}

function summarize(batches) {
  const map = new Map();
  const total = { label: "Total", operations: 0, advanced: 0, discount: 0, fee: 0, repasse: 0, financeCost: 0, termNum: 0, termDen: 0 };
  const add = (a, b, advanced, days) => {
    a.operations += 1;
    a.advanced += advanced;
    a.discount += Number(b.discount_amount ?? 0);
    a.fee += Number(b.fee_amount ?? 0);
    a.repasse += repasseOf(b);
    a.financeCost += financeCostOf(b);
    if (days != null) {
      a.termNum += advanced * days;
      a.termDen += advanced;
    }
  };
  for (const b of batches) {
    if (!CONFIRMED.has(b.status)) continue;
    const advanced = advancedAmountOf(b);
    if (!(advanced > 0.005)) continue;
    const name = b.institution?.trim() || "Sem instituição";
    if (!map.has(name)) {
      map.set(name, { label: name, operations: 0, advanced: 0, discount: 0, fee: 0, repasse: 0, financeCost: 0, termNum: 0, termDen: 0 });
    }
    const days = weightedTermDays(b);
    add(map.get(name), b, advanced, days);
    add(total, b, advanced, days);
  }
  const seal = (a) => {
    const financeCost = a.financeCost;
    const totalCost = financeCost + a.repasse;
    const termDays = a.termDen > 0 ? a.termNum / a.termDen : null;
    return {
      label: a.label,
      operations: a.operations,
      advanced: a.advanced,
      discount: a.discount,
      fee: a.fee,
      repasse: a.repasse,
      financeCost,
      totalCost,
      financePercent: a.advanced > 0.005 ? (financeCost / a.advanced) * 100 : null,
      totalPercent: a.advanced > 0.005 ? (totalCost / a.advanced) * 100 : null,
      termDays,
      financeMonthly: monthlyRate(financeCost, a.advanced, termDays),
      totalMonthly: monthlyRate(totalCost, a.advanced, termDays),
    };
  };
  return {
    groups: [...map.values()].map(seal).sort((x, y) => y.advanced - x.advanced),
    total: seal(total),
  };
}

// ---------------------------------------------------------------- dados reais

const LEPTA = "Lepta Multissetorial";
const DAYCOVAL = "Banco Daycoval";

// SGC 13 / borderô 11910 — base BRUTO, NFs 3403 e 3404.
const sgc13 = {
  institution: LEPTA,
  status: "OPEN",
  receive_date: "2026-06-05",
  received_amount: 430792.0,
  discount_amount: 58800.0,
  fee_amount: 408.0,
  repasse_enabled: true,
  repasse_amount: 34300.0,
  items: [
    { advanced_amount: 430000.0, due_date: "2026-08-30" },
    { advanced_amount: 60000.0, due_date: "2026-08-30" },
  ],
};

// SGC 14 / borderô 12187 — base LÍQUIDO, NF 3408 (bruto 88.937,90 → antecipado 83.468,22).
const sgc14 = {
  institution: LEPTA,
  status: "OPEN",
  receive_date: "2026-06-15",
  received_amount: 72827.95,
  discount_amount: 10238.77,
  fee_amount: 401.5,
  repasse_enabled: true,
  repasse_amount: 5842.78,
  items: [{ advanced_amount: 83468.22, due_date: "2026-09-10" }],
};

// Cessões Daycoval de junho, modeladas como o perfil DAYCOVAL realmente grava:
// deságio IMPLÍCITO (expected_amount − actual_received_amount), com discount_amount e
// fee_amount ZERADOS. Somar deságio + tarifas devolveria 0% aqui — é a regressão que
// estes casos protegem.
const day0306 = {
  institution: DAYCOVAL,
  status: "OPEN",
  receive_date: "2026-06-03",
  expected_amount: 114880.66,
  actual_received_amount: 107439.07,
  received_amount: 107439.07,
  discount_amount: 0,
  fee_amount: 0,
  repasse_enabled: false,
  repasse_amount: null,
  items: [
    { advanced_amount: 37308.58, due_date: "2026-08-05" },
    { advanced_amount: 77572.08, due_date: "2026-08-19" },
  ],
};

const day1206 = {
  institution: DAYCOVAL,
  status: "OPEN",
  receive_date: "2026-06-12",
  expected_amount: 230805.68,
  actual_received_amount: 214478.81,
  received_amount: 214478.81,
  discount_amount: 0,
  fee_amount: 0,
  repasse_enabled: false,
  repasse_amount: null,
  items: [
    { advanced_amount: 43478.08, due_date: "2026-08-26" },
    { advanced_amount: 187327.6, due_date: "2026-09-02" },
  ],
};

// Cessão sem o realizado informado: received_amount cai no previsto (regra 7 do handler),
// então ainda não há custo conhecido — não pode virar um deságio inventado.
const dayPrevisto = {
  ...day1206,
  receive_date: "2026-06-20",
  actual_received_amount: null,
  received_amount: 230805.68,
};

// Ruído que NÃO pode entrar em conta nenhuma.
const rascunho = { ...sgc13, status: "DRAFT" };
const cancelada = { ...sgc14, status: "CANCELLED" };

// ---------------------------------------------------------------- asserções

let failures = 0;
function check(what, got, want, tol = 0.01) {
  const ok = got != null && Math.abs(got - want) <= tol;
  if (!ok) failures += 1;
  const shown = got == null ? "null" : got.toFixed(4);
  console.log(`${ok ? "  ok  " : "FALHOU"} ${what}: ${shown} (esperado ${want})`);
}

console.log("\n— Lepta, junho/2026 (SGC 13 + 14) —");
const junho = summarize([sgc13, sgc14, day0306, day1206, rascunho, cancelada]);
const lepta = junho.groups.find((g) => g.label === LEPTA);
check("operações", lepta.operations, 2, 0);
check("valor antecipado", lepta.advanced, 573468.22, 0.02);
check("deságio + tarifas", lepta.financeCost, 69848.27, 0.02);
check("custo com repasse", lepta.totalCost, 109991.05, 0.02);
check("% da face (deságio + tarifas)", lepta.financePercent, 12.18, 0.01);
check("% da face (com repasse)", lepta.totalPercent, 19.18, 0.01);
check("prazo médio ponderado", lepta.termDays, 86.15, 0.05);
check("taxa mensal (deságio + tarifas)", lepta.financeMonthly, 4.63, 0.01);
check("taxa mensal (com repasse)", lepta.totalMonthly, 7.7, 0.01);

console.log("\n— Daycoval, junho/2026 (duas cessões) —");
const day = junho.groups.find((g) => g.label === DAYCOVAL);
check("operações", day.operations, 2, 0);
check("valor antecipado (face cedida)", day.advanced, 345686.34, 0.02);
check("deságio", day.financeCost, 23768.46, 0.02);
check("sem repasse, custo total = deságio", day.totalCost, 23768.46, 0.02);
check("% da face", day.financePercent, 6.88, 0.01);
check("prazo médio ponderado", day.termDays, 77.98, 0.05);
check("taxa mensal", day.financeMonthly, 2.78, 0.01);
// Regressão: o custo do Daycoval NÃO pode vir de discount_amount + fee_amount.
check("discount_amount somado é zero", day.discount ?? 0, 0, 0);
check("fee_amount somado é zero", day.fee ?? 0, 0, 0);

console.log("\n— Daycoval sem realizado informado —");
const semRealizado = summarize([dayPrevisto]);
check("face entra normalmente", semRealizado.total.advanced, 230805.68, 0.02);
check("custo ainda desconhecido = 0", semRealizado.total.financeCost, 0, 0.005);
console.log(
  `${semRealizado.total.financeMonthly == null ? "  ok  " : "FALHOU"} sem custo → sem taxa mensal: ${semRealizado.total.financeMonthly}`,
);
if (semRealizado.total.financeMonthly != null) failures += 1;

console.log("\n— Total do mês —");
check("operações (rascunho e cancelada fora)", junho.total.operations, 4, 0);
check("volume antecipado", junho.total.advanced, 919154.56, 0.02);
check("custo total com repasse", junho.total.totalCost, 133759.51, 0.02);
check("% da face", junho.total.totalPercent, 14.55, 0.01);

console.log("\n— Ordenação e casos de borda —");
check("maior volume primeiro (Lepta)", junho.groups[0].advanced, 573468.22, 0.02);
const vazio = summarize([rascunho, cancelada]);
check("só rascunho/cancelada → nenhum grupo", vazio.groups.length, 0, 0);
check("só rascunho/cancelada → total zerado", vazio.total.advanced, 0, 0);
const semPrazo = summarize([{ ...day0306, items: [{ advanced_amount: 114880.66, due_date: null }] }]);
check("NF sem vencimento → dinheiro conta", semPrazo.total.advanced, 114880.66, 0.02);
console.log(
  `${semPrazo.total.termDays == null ? "  ok  " : "FALHOU"} NF sem vencimento → prazo nulo: ${semPrazo.total.termDays}`,
);
if (semPrazo.total.termDays != null) failures += 1;
console.log(
  `${semPrazo.total.financeMonthly == null ? "  ok  " : "FALHOU"} sem prazo → sem taxa mensal: ${semPrazo.total.financeMonthly}`,
);
if (semPrazo.total.financeMonthly != null) failures += 1;

// Uma operação sem prazo não pode contaminar a média de quem tem.
const misto = summarize([sgc13, { ...sgc14, items: [{ advanced_amount: 83468.22, due_date: null }] }]);
check("prazo ignora operação sem vencimento", misto.total.termDays, 86.0, 0.05);

console.log(
  failures === 0
    ? "\nTodos os casos passaram.\n"
    : `\n${failures} caso(s) falharam.\n`,
);
process.exit(failures === 0 ? 0 : 1);
