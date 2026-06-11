import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * Ícone de ajuda (ⓘ) que recolhe textos explicativos/banners em um tooltip.
 * Abre por clique (toque) e por hover; fecha ao clicar fora ou Esc.
 */
export function HelpHint({ children, label = "Ajuda" }: { children: ReactNode; label?: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onEsc(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  return (
    <span
      ref={ref}
      className="relative inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        aria-label={label}
        onClick={() => setOpen((v) => !v)}
        className="flex h-5 w-5 items-center justify-center rounded-full border border-slate-300 text-[11px] font-semibold text-slate-500 hover:bg-slate-100 hover:text-slate-700"
      >
        i
      </button>
      {open ? (
        <span className="absolute left-1/2 top-7 z-30 w-72 -translate-x-1/2 rounded-lg border border-slate-200 bg-white p-3 text-xs leading-relaxed text-slate-600 shadow-lg">
          {children}
        </span>
      ) : null}
    </span>
  );
}
