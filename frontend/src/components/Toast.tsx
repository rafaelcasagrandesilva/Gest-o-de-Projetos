import { useEffect, type ReactNode } from "react";

/**
 * Toast simples e reutilizável (canto inferior direito, auto-dismiss).
 * Sem dependência externa — pode ser usado por qualquer módulo do SGC.
 */
export function Toast({
  open,
  title,
  onClose,
  children,
  durationMs = 8000,
}: {
  open: boolean;
  title: ReactNode;
  onClose: () => void;
  children?: ReactNode;
  durationMs?: number;
}) {
  useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(onClose, durationMs);
    return () => window.clearTimeout(t);
  }, [open, durationMs, onClose]);

  if (!open) return null;

  return (
    <div className="fixed bottom-4 right-4 z-[60] w-full max-w-sm rounded-xl border border-slate-200 bg-white p-4 shadow-lg">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-semibold text-slate-900">{title}</p>
        <button
          type="button"
          onClick={onClose}
          aria-label="Fechar"
          className="shrink-0 rounded p-0.5 text-slate-400 hover:text-slate-600"
        >
          <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4" aria-hidden>
            <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
          </svg>
        </button>
      </div>
      {children ? <div className="mt-2 text-sm text-slate-700">{children}</div> : null}
    </div>
  );
}
