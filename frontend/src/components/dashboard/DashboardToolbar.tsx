import type { ReactNode } from "react";
import { HelpHint } from "@/components/dashboard/HelpHint";

/**
 * Barra única de controle de dashboard (padrão Power BI / ERP):
 * título + ajuda (ⓘ) + meta + ações na primeira linha; filtros horizontais na segunda.
 * Substitui cabeçalhos em bloco e filtros empilhados.
 */
export function DashboardToolbar({
  title,
  hint,
  meta,
  actions,
  children,
}: {
  title: string;
  /** conteúdo do tooltip de ajuda (banners/explicações recolhidos) */
  hint?: ReactNode;
  /** texto curto à direita do título (ex.: "Competência 06/2026") */
  meta?: ReactNode;
  /** ações à direita (botões) */
  actions?: ReactNode;
  /** controles de filtro (linha horizontal, flex-wrap) */
  children?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="flex min-w-0 items-center gap-2">
          <h1 className="truncate text-lg font-semibold text-slate-900">{title}</h1>
          {hint ? <HelpHint>{hint}</HelpHint> : null}
          {meta ? <span className="text-xs font-medium text-indigo-700">{meta}</span> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      {children ? <div className="mt-2.5 flex flex-wrap items-end gap-x-4 gap-y-2">{children}</div> : null}
    </div>
  );
}

/** Campo compacto de filtro: label pequeno acima do controle, alinhado horizontalmente. */
export function ToolbarField({ label, children }: { label?: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      {label ? <span className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</span> : null}
      {children}
    </div>
  );
}
