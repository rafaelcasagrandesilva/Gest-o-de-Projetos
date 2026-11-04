import { useMemo } from "react";
import { formatCurrency, formatCurrencyShort } from "@/utils/currency";
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
  const basis = [charges, term].filter(Boolean).join(" · ");
  const tip = `${label} — ${basis}: ${formatCurrency(group.financeCost)} sobre ${formatCurrency(
    group.advanced,
  )} antecipados em ${ops}${term ? `, prazo médio de ${term}` : ""}.`;

  return (
    <div
      className={`rounded-lg border px-3 py-2 ${
        isConsolidated ? "border-slate-300 bg-white" : "border-slate-200 bg-slate-50"
      }`}
      title={tip}
    >
      <p className="max-w-[10.5rem] truncate text-[10px] font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </p>

      <p className="flex items-baseline gap-1.5 tabular-nums">
        <span className="text-lg font-semibold leading-tight text-slate-900">{pct(group.financePercent)}</span>
        <span className="text-[11px] text-slate-500">
          {group.financeMonthly == null ? "prazo indisponível" : `${pct(group.financeMonthly)} a.m.`}
        </span>
      </p>

      <p className="max-w-[10.5rem] truncate text-[10px] text-slate-500">{basis}</p>
      {/* A base ao lado do custo é o que impede a leitura errada de somar os
          percentuais: ela mostra que cada bloco tem um denominador diferente. */}
      <p className="whitespace-nowrap text-[10px] tabular-nums text-slate-500">
        {formatCurrency(group.financeCost)} de {formatCurrencyShort(group.advanced)}
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
