import type { ReactNode } from "react";

type Cols = 3 | 4 | 5 | 6;

const COLS_CLASS: Record<Cols, string> = {
  3: "grid-cols-2 sm:grid-cols-3",
  4: "grid-cols-2 sm:grid-cols-3 lg:grid-cols-4",
  5: "grid-cols-2 sm:grid-cols-3 lg:grid-cols-5",
  6: "grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6",
};

/**
 * Fileira densa de KPIs com colunas responsivas inteligentes.
 * `label` (opcional) é renderizado inline à esquerda da fileira (não em linha própria),
 * economizando espaço vertical em dashboards com vários grupos de KPI.
 */
export function KpiStrip({
  cols = 4,
  label,
  children,
}: {
  cols?: Cols;
  label?: string;
  children: ReactNode;
}) {
  if (label) {
    return (
      <div className="flex flex-col gap-2 lg:flex-row lg:items-stretch lg:gap-3">
        <span className="shrink-0 pt-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400 lg:w-24">
          {label}
        </span>
        <div className={`grid flex-1 gap-3 ${COLS_CLASS[cols]}`}>{children}</div>
      </div>
    );
  }
  return <div className={`grid gap-3 ${COLS_CLASS[cols]}`}>{children}</div>;
}

/** Card de KPI compacto (1 métrica): label pequeno + valor, altura reduzida. */
export function KpiCompact({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 shadow-sm">
      <p className="truncate text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-0.5 text-xl font-semibold tabular-nums ${accent ?? "text-slate-900"}`}>{value}</p>
      {sub ? <p className="mt-0.5 text-xs text-slate-500">{sub}</p> : null}
    </div>
  );
}
