import type { ReactNode } from "react";

/**
 * Cabeçalho padrão dos Dashboards Executivos (reutilizável).
 *
 * Reproduz o cabeçalho do protótipo: barra vertical de destaque + título forte,
 * subtítulo/período e descrição à esquerda; etiqueta à direita (ex.: "RELATÓRIO
 * EXECUTIVO · CONFIDENCIAL"). Genérico o suficiente para os futuros dashboards
 * (Projetos, Produção, Comercial, RH, Contratos, Clientes).
 */
export function DashboardHeader({
  title,
  subtitle,
  description,
  badge,
  actions,
}: {
  title: string;
  /** linha de período/contexto (ex.: "1º SEMESTRE DE 2026") */
  subtitle?: ReactNode;
  description?: ReactNode;
  /** etiqueta à direita (ex.: "RELATÓRIO EXECUTIVO · CONFIDENCIAL") */
  badge?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="rounded-xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-stretch gap-3">
          <span aria-hidden className="mt-0.5 w-1 shrink-0 rounded-full bg-indigo-600" />
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-bold uppercase tracking-tight text-slate-900">{title}</h1>
            <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
              {subtitle ? (
                <span className="text-xs font-semibold uppercase tracking-wide text-indigo-700">{subtitle}</span>
              ) : null}
              {description ? <span className="text-sm text-slate-500">{description}</span> : null}
            </div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {actions}
          {badge ? (
            <span className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">{badge}</span>
          ) : null}
        </div>
      </div>
    </header>
  );
}
