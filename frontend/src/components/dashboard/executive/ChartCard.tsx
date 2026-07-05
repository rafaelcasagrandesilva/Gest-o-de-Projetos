import type { ReactNode } from "react";

/**
 * Cartão padrão que envolve um gráfico dos Dashboards Executivos.
 * Título + subtítulo à esquerda, ações/legenda à direita, corpo abaixo.
 */
export function ChartCard({
  title,
  subtitle,
  aside,
  children,
  className,
}: {
  title: string;
  subtitle?: ReactNode;
  /** conteúdo à direita do cabeçalho (ex.: nota, toggle) */
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-xl border border-slate-200 bg-white p-4 shadow-sm ${className ?? ""}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
          {subtitle ? <p className="text-xs text-slate-500">{subtitle}</p> : null}
        </div>
        {aside ? <div className="shrink-0 text-xs text-slate-500">{aside}</div> : null}
      </div>
      <div className="mt-3">{children}</div>
    </section>
  );
}
