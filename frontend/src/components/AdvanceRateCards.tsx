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
 * novas aparecem sozinhas), seguidos de dois blocos consolidados que só diferem pelo
 * repasse — ver `RateVariant`.
 *
 * Derivam das MESMAS linhas já filtradas que alimentam a tabela — filtrar por mês
 * reescreve os números para aquele mês; "Todos" mostra o consolidado. Não há chamada de
 * API própria, então bloco e tabela não têm como divergir.
 */

const pct = (n: number | null): string =>
  n == null ? "—" : `${n.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;

/**
 * - `institution`: uma instituição, com o custo financeiro dela.
 * - `all`: TODAS as instituições, ainda sem o repasse.
 * - `total`: o fechamento — o anterior mais o repasse retido.
 *
 * `all` e `total` saem do MESMO consolidado, e a diferença entre os dois é exatamente o
 * repasse (por isso esses dois percentuais SE SOMAM: mesma base).
 *
 * Atenção ao ler: o percentual de `all` NÃO é a soma dos percentuais das instituições —
 * é a média deles ponderada pelo volume, e cai sempre ENTRE os dois. Só os valores em
 * reais é que somam. Foi por isso que o rótulo "Soma das instituições" saiu daqui: ele
 * prometia um percentual somável. Cada bloco mostra a própria base justamente para
 * deixar visível que os denominadores são diferentes.
 */
type RateVariant = "institution" | "all" | "total";

function RateStat({
  group,
  variant,
  institutions,
}: {
  group: AdvanceRateGroup;
  variant: RateVariant;
  /** Quantas instituições o consolidado abrange (só usado em `all` e `total`). */
  institutions?: number;
}) {
  const isTotal = variant === "total";
  const isConsolidated = variant !== "institution";
  const headline = isTotal ? group.totalPercent : group.financePercent;
  const monthly = isTotal ? group.totalMonthly : group.financeMonthly;
  const amount = isTotal ? group.totalCost : group.financeCost;

  // O Daycoval não cobra tarifa e registra o deságio de forma implícita, então nomear
  // "tarifas" ali seria falso. O rótulo segue o que existe de fato no recorte.
  const charges = group.fee > 0.005 ? "deságio + tarifas" : "deságio";
  const label =
    variant === "institution" ? group.label : variant === "all" ? "Todas as instituições" : "Custo total";
  const ops = `${group.operations} ${group.operations === 1 ? "operação" : "operações"}`;
  const term = group.termDays == null ? null : `${Math.round(group.termDays)} dias`;
  // Nos consolidados o rótulo já diz o alcance, então a composição encolhe para o que
  // os diferencia (o repasse) — é o que mantém os quatro blocos na linha dos filtros.
  const composition = isConsolidated ? (isTotal ? "com repasse" : "sem repasse") : charges;
  const basis = [composition, term].filter(Boolean).join(" · ");
  const tip = isTotal
    ? `Custo total = ${charges} (${formatCurrency(group.financeCost)}) + repasse retido (${formatCurrency(
        group.repasse,
      )}) = ${formatCurrency(group.totalCost)}, sobre ${formatCurrency(group.advanced)} antecipados em ${ops}${
        institutions && institutions > 1 ? ` de ${institutions} instituições` : ""
      }${term ? `, prazo médio de ${term}` : ""}.`
    : `${label} — ${basis}: ${formatCurrency(amount)} sobre ${formatCurrency(
        group.advanced,
      )} antecipados em ${ops}${term ? `, prazo médio de ${term}` : ""}.`;

  return (
    <div
      className={`rounded-lg border px-3 py-2 ${
        isTotal
          ? "border-indigo-200 bg-indigo-50"
          : isConsolidated
            ? "border-slate-300 bg-white"
            : "border-slate-200 bg-slate-50"
      }`}
      title={tip}
    >
      <p
        className={`max-w-[10.5rem] truncate text-[10px] font-semibold uppercase tracking-wide ${
          isTotal ? "text-indigo-700" : "text-slate-500"
        }`}
      >
        {label}
      </p>

      <p className="flex items-baseline gap-1.5 tabular-nums">
        <span className={`text-lg font-semibold leading-tight ${isTotal ? "text-indigo-900" : "text-slate-900"}`}>
          {pct(headline)}
        </span>
        <span className={`text-[11px] ${isTotal ? "text-indigo-600" : "text-slate-500"}`}>
          {monthly == null ? "prazo indisponível" : `${pct(monthly)} a.m.`}
        </span>
      </p>

      <p className={`max-w-[10.5rem] truncate text-[10px] ${isTotal ? "text-indigo-600" : "text-slate-500"}`}>
        {basis}
      </p>
      {/* A base ao lado do custo é o que impede a leitura errada de somar os
          percentuais: ela mostra que cada bloco tem um denominador diferente. */}
      <p className={`whitespace-nowrap text-[10px] tabular-nums ${isTotal ? "text-indigo-700" : "text-slate-500"}`}>
        {formatCurrency(amount)} de {formatCurrencyShort(group.advanced)}
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
  // repetiria o bloco dela. O total só diz algo quando existe repasse — sem ele, seria
  // idêntico ao consolidado.
  const showAll = groups.length > 1;
  const showTotal = total.repasse > 0.005;

  return (
    <div className="flex flex-wrap items-start gap-2 sm:ml-auto">
      {groups.map((g) => (
        <RateStat key={g.label} group={g} variant="institution" />
      ))}
      {showAll && <RateStat group={total} variant="all" institutions={groups.length} />}
      {showTotal && <RateStat group={total} variant="total" institutions={groups.length} />}
    </div>
  );
}
