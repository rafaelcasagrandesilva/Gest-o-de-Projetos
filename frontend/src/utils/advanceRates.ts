import type { AdvanceBatch, AdvanceBatchStatus } from "@/services/receivableAdvanceBatches";

/**
 * Taxas efetivas das operações de antecipação (indicadores da tela de Antecipações).
 *
 * As duas fórmulas abaixo valem para QUALQUER perfil de instituição — é o que permite
 * comparar Lepta e Daycoval no mesmo indicador, apesar de o custo ser registrado de
 * formas completamente diferentes nos dois:
 *
 *   base  = Σ `items[].advanced_amount`  (o "Nominal"/"Total Bruto" da operação)
 *   custo = base − `received_amount`     (o que a operação comeu antes de virar caixa)
 *
 * Por que funciona nos dois perfis:
 *  - LEPTA grava o custo explicitamente e o líquido obedece a `_net_received()`
 *    (advanced − deságio − tarifas), então base − received = deságio + tarifas.
 *  - DAYCOVAL não usa `discount_amount`/`fee_amount` — o deságio é implícito, na
 *    diferença entre `expected_amount` (face cedida) e `actual_received_amount`. Como
 *    `received_amount` do Daycoval é o realizado (ou o previsto, enquanto o realizado
 *    não for informado), base − received devolve exatamente esse deságio implícito.
 *    Somar `discount_amount + fee_amount` daria ZERO para toda operação Daycoval.
 * Verificado contra os 17 borderôs reais: `Σ advanced_amount` bate com
 * `received + discount + fee` e `base − received` bate com `deságio + tarifas`, centavo
 * a centavo, em todos.
 *
 * NÃO use `gross_amount` (soma do BRUTO das NFs) como denominador: quando a base da
 * operação é LÍQUIDO ou LÍQUIDO−10% os dois divergem e o percentual sai subestimado.
 * É por isso que estes números não batem com o campo `discount_percent` da tabela, que
 * usa `gross_amount` — a divergência é conhecida e está restrita àquela coluna.
 */

/** Só operações confirmadas custaram dinheiro: DRAFT é rascunho, CANCELLED foi revertida.
 * Espelha CONFIRMED_BATCH_STATUSES em app/models/receivable_advance_batch.py. */
const CONFIRMED: ReadonlySet<AdvanceBatchStatus> = new Set<AdvanceBatchStatus>(["OPEN", "SETTLED"]);

const DAY_MS = 86_400_000;

export interface AdvanceRateGroup {
  /** Nome da instituição, ou "Total" no consolidado. */
  label: string;
  operations: number;
  /** Soma dos valores antecipados (base de todos os percentuais). */
  advanced: number;
  /** Deságio explícito. Sempre 0 no perfil DAYCOVAL — use `financeCost`, não estes. */
  discount: number;
  /** Tarifas bancárias explícitas. Sempre 0 no perfil DAYCOVAL. */
  fee: number;
  repasse: number;
  /** Custo financeiro (antecipado − creditado): o "juros" da operação, em qualquer perfil. */
  financeCost: number;
  /** Deságio + tarifas + repasse — o custo de caixa. */
  totalCost: number;
  /** financeCost ÷ advanced, em %. */
  financePercent: number | null;
  /** totalCost ÷ advanced, em %. */
  totalPercent: number | null;
  /** Prazo médio ponderado pelo valor antecipado de cada NF, em dias. */
  termDays: number | null;
  /** Taxa mensal equivalente de financeCost, em % a.m. */
  financeMonthly: number | null;
  /** Taxa mensal equivalente de totalCost, em % a.m. */
  totalMonthly: number | null;
}

/** "YYYY-MM-DD" → epoch UTC. Evita o deslocamento de fuso do `new Date(iso)` local. */
function isoToUtc(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return null;
  return Date.UTC(y, m - 1, d);
}

/**
 * Valor antecipado da operação (Nominal do borderô) = soma do antecipado por NF.
 *
 * O fallback `received + deságio + tarifas` serve a operações antigas cujos itens ainda
 * não têm `advanced_amount` congelado; ele é exato no perfil LEPTA e por isso é seguro
 * como rede, mas devolveria a face ERRADA no Daycoval, onde deságio e tarifas são zero.
 */
export function advancedAmountOf(b: AdvanceBatch): number {
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

/**
 * Custo financeiro da operação = antecipado − creditado.
 *
 * Cobre o deságio explícito da Lepta e o implícito do Daycoval de uma vez só. Não inclui
 * o repasse, que não sai do valor creditado (é retido à parte, no Ledger de Repasse).
 */
export function financeCostOf(b: AdvanceBatch): number {
  const cost = advancedAmountOf(b) - Number(b.received_amount ?? 0);
  return cost > 0 ? cost : 0;
}

/** Repasse congelado na confirmação; zero quando a operação não tem repasse. */
export function repasseOf(b: AdvanceBatch): number {
  return b.repasse_enabled ? Number(b.repasse_amount ?? 0) : 0;
}

/**
 * Prazo médio da operação, em dias, ponderado pelo valor antecipado de cada NF.
 *
 * Calculado a partir do vencimento das NFs (`items[].due_date`) e NÃO de `repayment_date`:
 * esse campo vem preenchido igual à data da operação em boa parte dos borderôs, o que
 * produziria prazo zero. NFs sem vencimento ficam fora da ponderação (mas continuam
 * contando no dinheiro).
 */
export function weightedTermDays(b: AdvanceBatch): number | null {
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

/**
 * Taxa mensal equivalente, em regime composto de 30 dias.
 *
 * O juro incide sobre o que ENTROU no caixa (`advanced − cost`), não sobre a face —
 * é o que torna instituições de prazos diferentes comparáveis entre si.
 */
export function monthlyRate(cost: number, advanced: number, termDays: number | null): number | null {
  if (termDays == null || !(termDays > 0)) return null;
  const net = advanced - cost;
  if (!(net > 0) || !(cost > 0)) return null;
  return ((1 + cost / net) ** (30 / termDays) - 1) * 100;
}

function emptyGroup(label: string): AdvanceRateGroup {
  return {
    label,
    operations: 0,
    advanced: 0,
    discount: 0,
    fee: 0,
    repasse: 0,
    financeCost: 0,
    totalCost: 0,
    financePercent: null,
    totalPercent: null,
    termDays: null,
    financeMonthly: null,
    totalMonthly: null,
  };
}

/** Acumulador: o prazo tem ponderação própria porque operações sem vencimento nas NFs
 * entram no dinheiro mas ficam de fora da média de prazo. */
interface Acc {
  g: AdvanceRateGroup;
  /** Σ (valor antecipado × prazo em dias). */
  termNum: number;
  /** Σ (valor antecipado) — só das operações que têm prazo. */
  termDen: number;
}

function newAcc(label: string): Acc {
  return { g: emptyGroup(label), termNum: 0, termDen: 0 };
}

function add(acc: Acc, b: AdvanceBatch, advanced: number, days: number | null): void {
  acc.g.operations += 1;
  acc.g.advanced += advanced;
  acc.g.discount += Number(b.discount_amount ?? 0);
  acc.g.fee += Number(b.fee_amount ?? 0);
  acc.g.repasse += repasseOf(b);
  acc.g.financeCost += financeCostOf(b);
  if (days != null) {
    acc.termNum += advanced * days;
    acc.termDen += advanced;
  }
}

/** Fecha os percentuais e as taxas de um acumulador já somado. */
function seal({ g, termNum, termDen }: Acc): AdvanceRateGroup {
  g.totalCost = g.financeCost + g.repasse;
  if (g.advanced > 0.005) {
    g.financePercent = (g.financeCost / g.advanced) * 100;
    g.totalPercent = (g.totalCost / g.advanced) * 100;
  }
  g.termDays = termDen > 0 ? termNum / termDen : null;
  g.financeMonthly = monthlyRate(g.financeCost, g.advanced, g.termDays);
  g.totalMonthly = monthlyRate(g.totalCost, g.advanced, g.termDays);
  return g;
}

/**
 * Consolida as operações por instituição e no total.
 *
 * Recebe as linhas JÁ FILTRADAS pela tela (período + instituição), de modo que os cards
 * sempre descrevem exatamente o mesmo recorte que a tabela abaixo deles.
 */
export function summarizeAdvanceRates(batches: AdvanceBatch[]): {
  groups: AdvanceRateGroup[];
  total: AdvanceRateGroup;
} {
  const byInstitution = new Map<string, Acc>();
  const total = newAcc("Total");

  for (const b of batches) {
    if (!CONFIRMED.has(b.status)) continue;
    const advanced = advancedAmountOf(b);
    if (!(advanced > 0.005)) continue;

    const name = b.institution?.trim() || "Sem instituição";
    let acc = byInstitution.get(name);
    if (!acc) {
      acc = newAcc(name);
      byInstitution.set(name, acc);
    }

    const days = weightedTermDays(b);
    add(acc, b, advanced, days);
    add(total, b, advanced, days);
  }

  const groups = [...byInstitution.values()].map(seal).sort((a, b) => b.advanced - a.advanced);
  return { groups, total: seal(total) };
}
