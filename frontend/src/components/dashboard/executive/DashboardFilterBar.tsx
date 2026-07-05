import type { ReactNode } from "react";

/**
 * Barra de filtros globais reutilizável dos Dashboards Executivos.
 *
 * Layout horizontal com flex-wrap (responsivo). Os controles são passados como
 * children (`FilterField`), o que mantém a arquitetura aberta para adicionar
 * novos filtros no futuro (Empresa, Cliente…) sem refazer o dashboard.
 */
export function DashboardFilterBar({
  children,
  actions,
}: {
  children: ReactNode;
  /** ações à direita (ex.: limpar filtros) */
  actions?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
      <div className="flex flex-wrap items-end gap-x-4 gap-y-3">
        {children}
        {actions ? <div className="ml-auto flex items-end gap-2">{actions}</div> : null}
      </div>
    </div>
  );
}

/** Campo de filtro compacto: label pequeno acima do controle. */
export function FilterField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex min-w-0 flex-col gap-1">
      <span className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</span>
      {children}
    </label>
  );
}
