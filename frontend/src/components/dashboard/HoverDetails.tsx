import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";

/**
 * Detalhamento ao passar o mouse (ou focar pelo teclado) sobre um rótulo.
 *
 * Substitui o `title` nativo quando o conteúdo é tabular: título, tabela com colunas numéricas
 * alinhadas à direita (tabular-nums) e rodapé opcional. O popover é `absolute` abaixo do gatilho
 * (ou acima, se faltar espaço) e é deslocado na horizontal para não sair da janela.
 */

export interface HoverDetailsRow {
  key?: string;
  label: ReactNode;
  /** Uma célula por coluna numérica. */
  values: ReactNode[];
  /** Linha de total: negrito com divisória acima. */
  emphasis?: boolean;
}

export interface HoverDetailsProps {
  /** Rótulo que dispara o detalhamento. */
  children: ReactNode;
  title?: ReactNode;
  /** Linha logo abaixo do título (ex.: "Carga efetiva 14,53% da receita"). */
  subtitle?: ReactNode;
  /** Cabeçalho das colunas numéricas (opcional). */
  columns?: ReactNode[];
  rows?: HoverDetailsRow[];
  footer?: ReactNode;
  className?: string;
}

const VIEWPORT_MARGIN = 8;

export function HoverDetails({ children, title, subtitle, columns, rows = [], footer, className }: HoverDetailsProps) {
  const [open, setOpen] = useState(false);
  const [placeAbove, setPlaceAbove] = useState(false);
  const [shiftX, setShiftX] = useState(0);
  const popRef = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    function onEsc(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", onEsc);
    return () => document.removeEventListener("keydown", onEsc);
  }, [open]);

  // Mede já na posição padrão (abaixo, alinhado à esquerda) e corrige antes da pintura.
  useLayoutEffect(() => {
    if (!open) {
      setShiftX(0);
      setPlaceAbove(false);
      return;
    }
    const el = popRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const vw = document.documentElement.clientWidth;
    let dx = 0;
    if (r.right > vw - VIEWPORT_MARGIN) dx = vw - VIEWPORT_MARGIN - r.right;
    if (r.left + dx < VIEWPORT_MARGIN) dx = VIEWPORT_MARGIN - r.left;
    setShiftX(dx);
    const triggerTop = r.top - (el.offsetTop || 0);
    setPlaceAbove(r.bottom > window.innerHeight - VIEWPORT_MARGIN && triggerTop - r.height > VIEWPORT_MARGIN);
  }, [open]);

  const colCount = Math.max(columns?.length ?? 0, ...rows.map((r) => r.values.length), 0);

  return (
    <span
      className={`relative inline-flex ${className ?? ""}`}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <span
        tabIndex={0}
        aria-describedby={open ? id : undefined}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="cursor-help rounded-sm underline decoration-slate-300 decoration-dotted underline-offset-4 outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
      >
        {children}
      </span>
      {open ? (
        // Faixa transparente (pt/pb) liga gatilho e popover: o mouse atravessa sem fechar.
        <div
          ref={popRef}
          className={`absolute left-0 z-50 ${placeAbove ? "bottom-full pb-1.5" : "top-full pt-1.5"}`}
          style={{ transform: shiftX ? `translateX(${shiftX}px)` : undefined }}
        >
          <div
            id={id}
            role="tooltip"
            className="w-max min-w-[15rem] max-w-[22rem] rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-xs font-normal leading-snug text-slate-600 shadow-lg"
          >
            {title ? <p className="font-semibold text-slate-800">{title}</p> : null}
            {subtitle ? <p className="mt-0.5 text-[11px] text-slate-500">{subtitle}</p> : null}
            {rows.length > 0 ? (
              <table className={`w-full border-collapse ${title || subtitle ? "mt-2" : ""}`}>
                {columns && columns.length > 0 ? (
                  <thead>
                    <tr className="text-[10px] uppercase tracking-wide text-slate-400">
                      <th className="pb-1 pr-3 text-left font-medium" />
                      {columns.map((c, i) => (
                        <th key={i} className="pb-1 pl-3 text-right font-medium">
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                ) : null}
                <tbody>
                  {rows.map((r, ri) => (
                    <tr
                      key={r.key ?? ri}
                      className={r.emphasis ? "border-t border-slate-200 font-semibold text-slate-900" : undefined}
                    >
                      <td className={`pr-3 text-left ${r.emphasis ? "pt-1.5" : "py-0.5"}`}>{r.label}</td>
                      {Array.from({ length: colCount }, (_, ci) => (
                        <td
                          key={ci}
                          className={`whitespace-nowrap pl-3 text-right tabular-nums ${r.emphasis ? "pt-1.5" : "py-0.5"} ${
                            r.emphasis ? "" : ci === 0 ? "text-slate-800" : "text-slate-500"
                          }`}
                        >
                          {r.values[ci] ?? ""}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
            {footer ? (
              <p className={`text-[11px] leading-snug text-slate-500 ${rows.length || title || subtitle ? "mt-2" : ""}`}>
                {footer}
              </p>
            ) : null}
          </div>
        </div>
      ) : null}
    </span>
  );
}
