import type { ReactNode } from "react";

/**
 * Card de KPI dos Dashboards Executivos (reutilizável).
 *
 * Reproduz o rodapé do protótipo: barra de cor no topo, nome do indicador,
 * valor acumulado e pílula de crescimento. Preparado para drill-down futuro
 * (quando `onClick` é informado, o card fica clicável).
 */
export function KpiCard({
  label,
  value,
  deltaPct,
  deltaSuffix = "no período",
  /** cor da série (barra superior + acento) */
  color,
  onClick,
}: {
  label: string;
  value: string;
  /** crescimento (%). null = indefinido (sem base) → sem pílula */
  deltaPct?: number | null;
  deltaSuffix?: string;
  color: string;
  onClick?: () => void;
}) {
  const clickable = typeof onClick === "function";
  return (
    <div
      role={clickable ? "button" : undefined}
      tabIndex={clickable ? 0 : undefined}
      onClick={onClick}
      onKeyDown={clickable ? (e) => (e.key === "Enter" || e.key === " ") && onClick?.() : undefined}
      className={`overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm ${
        clickable ? "cursor-pointer transition hover:shadow-md focus:outline-none focus:ring-2 focus:ring-indigo-400" : ""
      }`}
    >
      <div className="h-1 w-full" style={{ backgroundColor: color }} />
      <div className="px-4 py-3">
        <div className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
          <p className="truncate text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</p>
        </div>
        <p className="mt-1 text-2xl font-bold tabular-nums text-slate-900">{value}</p>
        {deltaPct !== undefined ? (
          <div className="mt-1.5 flex items-center gap-2">
            <DeltaPill pct={deltaPct} />
            <span className="text-[11px] text-slate-400">{deltaSuffix}</span>
          </div>
        ) : null}
      </div>
    </div>
  );
}

/** Pílula de variação percentual: verde para alta, vermelho para queda, cinza para indefinido. */
export function DeltaPill({ pct }: { pct: number | null }): ReactNode {
  if (pct === null || !Number.isFinite(pct)) {
    return (
      <span className="inline-flex items-center rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] font-semibold text-slate-500">
        —
      </span>
    );
  }
  const up = pct >= 0;
  const cls = up ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700";
  const arrow = up ? "▲" : "▼";
  const formatted = `${up ? "+" : ""}${Math.round(pct)}%`;
  return (
    <span className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-semibold ${cls}`}>
      <span aria-hidden>{arrow}</span>
      {formatted}
    </span>
  );
}
