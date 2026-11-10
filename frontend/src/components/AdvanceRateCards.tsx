import { useMemo } from "react";
import { formatCurrency } from "@/utils/currency";
import { summarizeAdvanceRates, type AdvanceRateGroup } from "@/utils/advanceRates";
import type { AdvanceBatch } from "@/services/receivableAdvanceBatches";

/**
 * Taxa efetiva das operações de antecipação, em blocos compactos que moram DENTRO da
 * barra de filtros — de propósito: assim os indicadores não empurram a tabela de
 * operações para baixo.
 *
 * Um bloco por instituição presente no recorte (nada é fixo no código: instituições
 * novas aparecem sozinhas), seguido do consolidado de todas — ver `RateVariant`.
 *
 * Derivam das MESMAS linhas já filtradas que alimentam a tabela — filtrar por mês
 * reescreve os números para aquele mês; "Todos" mostra o consolidado. Não há chamada de
 * API própria, então bloco e tabela não têm como divergir.
 */

const pct = (n: number | null): string =>
  n == null ? "—" : `${n.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;

/**
 * - `institution`: uma instituição, com o custo financeiro dela.
 * - `all`: TODAS as instituições juntas.
 *
 * Só deságio e tarifas entram na taxa. O repasse retido NÃO é juros (decisão da diretoria,
 * 03/11/2026): o bloco "Custo total" (custo + repasse) foi removido daqui.
 *
 * Atenção ao ler: o percentual de `all` NÃO é a soma dos percentuais das instituições —
 * é a média deles ponderada pelo volume, e cai sempre ENTRE os dois. Só os valores em
 * reais é que somam. Cada bloco mostra a própria base justamente para deixar visível que
 * os denominadores são diferentes.
 */
type RateVariant = "institution" | "all";

function RateStat({ group, variant }: { group: AdvanceRateGroup; variant: RateVariant }) {
  const isConsolidated = variant === "all";

  // O Daycoval não cobra tarifa e registra o deságio de forma implícita, então nomear
  // "tarifas" ali seria falso. O rótulo segue o que existe de fato no recorte.
  const charges = group.fee > 0.005 ? "deságio + tarifas" : "deságio";
  const label = isConsolidated ? "Todas as instituições" : group.label;
  const ops = `${group.operations} ${group.operations === 1 ? "operação" : "operações"}`;
  const term = group.termDays == null ? null : `${Math.round(group.termDays)} dias`;
  const nfs = `${group.invoices} ${group.invoices === 1 ? "NF" : "NFs"}`;
  const credited = group.advanced - group.financeCost;
  const tip = `${label} — antecipado ${formatCurrency(group.advanced)} em ${ops} (${nfs}); creditado ${formatCurrency(
    credited,
  )}. Custo (${charges}): ${formatCurrency(group.financeCost)}${term ? `, prazo médio de ${term}` : ""}.`;

  return (
    <div
      className={`rounded-lg border px-3 py-2 ${
        isConsolidated ? "border-indigo-200 bg-indigo-50/60" : "border-slate-200 bg-slate-50"
      }`}
      title={tip}
    >
      <p className="max-w-[12rem] truncate text-[10px] font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </p>

      {/* Quanto já foi antecipado: o número que a pessoa procura primeiro. */}
      <p className="whitespace-nowrap text-base font-semibold leading-tight tabular-nums text-slate-900">
        {formatCurrency(group.advanced)}
      </p>
      <p className="whitespace-nowrap text-[10px] tabular-nums text-slate-500">
        antecipado · {ops} · {nfs}
      </p>

      {/* Taxa efetiva. A base (o antecipado logo acima) é o que impede somar os
          percentuais: cada bloco tem um denominador diferente. */}
      <p className="whitespace-nowrap text-[11px] tabular-nums text-slate-600">
        <span className="font-semibold text-slate-900">{pct(group.financePercent)}</span>
        {" · "}
        {group.financeMonthly == null ? "prazo indisponível" : `${pct(group.financeMonthly)} a.m.`}
        {term ? ` · ${term}` : ""}
      </p>
      <p className="whitespace-nowrap text-[10px] tabular-nums text-slate-500">
        {charges} {formatCurrency(group.financeCost)}
      </p>
    </div>
  );
}

export function AdvanceRateCards({ batches }: { batches: AdvanceBatch[] }) {
  const { groups, total } = useMemo(() => summarizeAdvanceRates(batches), [batches]);

  // Sem operação confirmada no recorte não há taxa para mostrar; a tabela abaixo já
  // explica que o filtro não trouxe nada.
  if (groups.length === 0) return null;

  // O consolidado só diz algo quando há mais de uma instituição — com uma só ele
  // repetiria o bloco dela.
  const showAll = groups.length > 1;

  return (
    <div className="flex flex-wrap items-start gap-2 sm:ml-auto">
      {groups.map((g) => (
        <RateStat key={g.label} group={g} variant="institution" />
      ))}
      {showAll && <RateStat group={total} variant="all" />}
    </div>
  );
}
