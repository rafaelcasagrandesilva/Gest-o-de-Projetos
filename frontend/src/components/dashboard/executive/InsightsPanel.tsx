import type { ReactNode } from "react";

export interface InsightItem {
  /** rótulo do destaque (ex.: "Maior faturamento") */
  label: string;
  /** valor principal (ex.: "R$ 657 mil") */
  value: string;
  /** meta à direita (ex.: "JUN") */
  meta?: string;
  /** cor do marcador (opcional) */
  color?: string;
}

/**
 * Painel "Insights" reutilizável (era "Visão Geral" no protótipo).
 *
 * Destaques calculados automaticamente no backend. A arquitetura fica preparada
 * para, no futuro, receber insights gerados por IA — basta alimentar `items`.
 */
export function InsightsPanel({
  title = "Insights",
  headline,
  items,
  footer,
}: {
  title?: string;
  /** bloco de destaque no topo (ex.: crescimento acumulado) */
  headline?: { label: string; value: string; meta?: string };
  items: InsightItem[];
  footer?: ReactNode;
}) {
  return (
    <section className="flex flex-col rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">{title}</h3>

      {headline ? (
        <div className="mt-3 border-b border-slate-100 pb-3">
          <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{headline.label}</p>
          <div className="mt-0.5 flex items-baseline gap-2">
            <span className="text-3xl font-bold tracking-tight text-indigo-600">{headline.value}</span>
            {headline.meta ? <span className="text-xs font-medium text-slate-400">{headline.meta}</span> : null}
          </div>
        </div>
      ) : null}

      <ul className="mt-3 space-y-2.5">
        {items.map((it, i) => (
          <li key={`${it.label}-${i}`} className="flex items-start justify-between gap-3">
            <div className="flex min-w-0 items-start gap-2">
              <span
                aria-hidden
                className="mt-1.5 h-2 w-2 shrink-0 rounded-full"
                style={{ backgroundColor: it.color ?? "#94a3b8" }}
              />
              <div className="min-w-0">
                <p className="truncate text-xs text-slate-500">{it.label}</p>
                <p className="truncate text-sm font-semibold text-slate-900">{it.value}</p>
              </div>
            </div>
            {it.meta ? (
              <span className="shrink-0 pt-0.5 text-[11px] font-medium uppercase tracking-wide text-slate-400">
                {it.meta}
              </span>
            ) : null}
          </li>
        ))}
      </ul>

      {footer ? <div className="mt-auto pt-3">{footer}</div> : null}
    </section>
  );
}
