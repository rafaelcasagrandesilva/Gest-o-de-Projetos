import { Money } from "@/components/Money";
import { formatCurrency } from "@/utils/currency";
import type { Revenue } from "@/services/financial";

/**
 * Conferência entre o faturamento digitado pelo gestor e a soma das NFs emitidas no mês.
 *
 * Entram apenas NFs **faturadas** — pré-faturada (`is_official = false`) e cancelada ficam de
 * fora — e a competência considerada é a da NF, nunca o mês da emissão: a nota costuma ser
 * emitida cerca de um mês depois do serviço.
 *
 * Três estados, e o terceiro importa tanto quanto os outros: no mês corrente é NORMAL ainda não
 * haver NF emitida, então "sem NF" é neutro, e não uma divergência.
 */

/** Diferença abaixo de um centavo é arredondamento, não divergência. */
const TOL = 0.005;

export type NfMatch = "match" | "diff" | "none" | "hidden";

export function nfMatchOf(r: Revenue): NfMatch {
  // Sem "Dados sensíveis" os valores chegam redigidos: não há o que conferir.
  if (r.amount == null || r.nf_amount == null) {
    return r.nf_amount === null && r.amount != null ? "none" : "hidden";
  }
  return Math.abs(r.nf_amount - r.amount) < TOL ? "match" : "diff";
}

const DOT: Record<Exclude<NfMatch, "hidden">, { cls: string; label: string }> = {
  match: { cls: "bg-emerald-500", label: "Confere com as NFs do mês" },
  diff: { cls: "bg-red-500", label: "Diverge das NFs do mês" },
  none: { cls: "bg-slate-300", label: "Nenhuma NF faturada nesta competência" },
};

export function RevenueNfCell({ revenue }: { revenue: Revenue }) {
  const match = nfMatchOf(revenue);

  if (match === "hidden") {
    return <Money value={null} />;
  }
  if (match === "none") {
    return (
      <span className="flex items-center justify-end gap-2 text-slate-400" title={DOT.none.label}>
        <span className={`h-2 w-2 shrink-0 rounded-full ${DOT.none.cls}`} />
        <span className="text-xs">sem NF</span>
      </span>
    );
  }

  const diff = (revenue.nf_amount ?? 0) - (revenue.amount ?? 0);
  const meta = DOT[match];
  const title =
    match === "match"
      ? meta.label
      : `${meta.label}: ${diff > 0 ? "as NFs somam" : "o manual está"} ${formatCurrency(
          Math.abs(diff),
        )} ${diff > 0 ? "a mais que o valor informado" : "acima do que foi faturado"}.`;

  return (
    <span className="flex items-center justify-end gap-2" title={title}>
      <span className={`h-2 w-2 shrink-0 rounded-full ${meta.cls}`} />
      <Money value={revenue.nf_amount} />
    </span>
  );
}
