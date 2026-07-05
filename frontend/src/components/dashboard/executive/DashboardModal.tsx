import { useEffect, type ReactNode } from "react";

/**
 * Modal quase full-screen reutilizável para "expandir" gráficos/painéis dos
 * Dashboards Executivos. Fecha no Esc e no clique do backdrop. Genérico para os
 * futuros dashboards do módulo Indicadores.
 */
export function DashboardModal({
  open,
  title,
  onClose,
  actions,
  children,
}: {
  open: boolean;
  title: ReactNode;
  onClose: () => void;
  /** controles à direita do cabeçalho (ex.: resetar zoom, toggles) */
  actions?: ReactNode;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    function onEsc(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onEsc);
    // Evita rolagem do body enquanto o modal está aberto.
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onEsc);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-3 sm:p-6"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
    >
      <div className="flex h-full max-h-[94vh] w-full max-w-[96vw] flex-col rounded-xl border border-slate-200 bg-white shadow-xl">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
          <div className="flex flex-wrap items-center gap-2">
            {actions}
            <button
              type="button"
              onClick={onClose}
              className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
              aria-label="Fechar"
            >
              <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4" aria-hidden>
                <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
              </svg>
              Fechar
            </button>
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-4">{children}</div>
      </div>
    </div>
  );
}
