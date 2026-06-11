import type { ConsolidatedRoi } from "@/services/indicators";
import { formatCurrency } from "@/utils/currency";
import { formatRoiPct, roiTone } from "@/utils/roiFormat";

function Metric({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="min-w-0">
      <p className="truncate text-xs font-medium uppercase tracking-wide text-indigo-100/80">{label}</p>
      <p className={`mt-1 whitespace-nowrap text-base font-semibold tabular-nums ${accent ?? "text-white"}`}>
        {value}
      </p>
    </div>
  );
}

/**
 * Card executivo consolidado (topo da página).
 * ROI consolidado = Σ lucro / Σ custo (nunca média de ROIs).
 */
export function ConsolidatedRoiCard({
  data,
  title,
  subtitle,
}: {
  data: ConsolidatedRoi;
  title: string;
  subtitle?: string;
}) {
  const tone = roiTone(data.roi);
  const roiColor =
    tone.key === "verde"
      ? "text-emerald-300"
      : tone.key === "amarelo"
        ? "text-amber-300"
        : tone.key === "vermelho"
          ? "text-rose-300"
          : "text-slate-300";

  return (
    <div className="rounded-2xl border border-indigo-700 bg-gradient-to-br from-indigo-700 to-indigo-900 p-6 shadow-md">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-indigo-100">{title}</h2>
          {subtitle ? <p className="mt-0.5 text-xs text-indigo-200/80">{subtitle}</p> : null}
        </div>
        <span className="rounded-full bg-white/10 px-3 py-1 text-xs font-medium text-indigo-50">
          {data.project_count} projeto(s)
        </span>
      </div>

      <div className="mt-4 flex flex-col gap-4 lg:flex-row lg:items-end lg:gap-4">
        <div className="shrink-0">
          <p className="text-xs font-medium uppercase tracking-wide text-indigo-100/80">
            ROI Operacional Consolidado
          </p>
          <p className={`mt-1 text-5xl font-bold tabular-nums ${roiColor}`}>{formatRoiPct(data.roi_pct)}</p>
        </div>
        <div className="grid w-full grid-cols-2 gap-x-6 gap-y-4 lg:grid-cols-4">
          <Metric label="Receita consolidada" value={formatCurrency(data.revenue)} />
          <Metric label="Custo consolidado" value={formatCurrency(data.cost)} />
          <Metric
            label="Lucro operacional consolidado"
            value={formatCurrency(data.operational_profit)}
            accent={data.operational_profit < 0 ? "text-rose-300" : "text-white"}
          />
          <Metric label="Qtd. de projetos" value={String(data.project_count)} />
        </div>
      </div>
    </div>
  );
}
