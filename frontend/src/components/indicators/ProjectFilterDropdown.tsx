import { useEffect, useRef, useState } from "react";

export type ProjectOption = { id: string; name: string };

/**
 * Dropdown multiselect de projetos (checkboxes), integrado à barra de filtros.
 * Sem "Selecionar todos / Limpar" — apenas seleção individual.
 */
export function ProjectFilterDropdown({
  options,
  selected,
  onToggle,
  emptyText = "Nenhum projeto",
  noOptionsText = "Nenhum projeto ativo.",
  disabled = false,
  disabledTitle,
}: {
  options: ProjectOption[];
  selected: Set<string>;
  onToggle: (id: string) => void;
  /** rótulo quando nada está selecionado (ex.: "Todos os centros") */
  emptyText?: string;
  /** rótulo quando não há opções */
  noOptionsText?: string;
  /** Bloqueia a seleção (ex.: modo Contas a Pagar, que é sempre da empresa inteira). */
  disabled?: boolean;
  /** Explica ao usuário POR QUE está bloqueado (vira o title do botão). */
  disabledTitle?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onEsc(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  const count = selected.size;
  const total = options.length;

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={disabled}
        title={disabled ? disabledTitle : undefined}
        className="flex min-w-[180px] items-center justify-between gap-2 rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-800 hover:bg-slate-50 focus:border-indigo-500 focus:outline-none disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="truncate">
          {count === 0
            ? emptyText
            : count === total
              ? `Todos (${total})`
              : `${count} de ${total} selecionados`}
        </span>
        <svg
          className={`h-4 w-4 shrink-0 text-slate-400 transition-transform ${open ? "rotate-180" : ""}`}
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10 11.17l3.71-3.94a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {open && (
        <div
          className="absolute z-20 mt-1 max-h-64 w-[min(20rem,80vw)] overflow-y-auto rounded-lg border border-slate-200 bg-white p-1 shadow-lg"
          role="listbox"
        >
          {options.length === 0 ? (
            <p className="px-3 py-2 text-sm text-slate-500">{noOptionsText}</p>
          ) : (
            options.map((opt) => (
              <label
                key={opt.id}
                className="flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
              >
                <input
                  type="checkbox"
                  checked={selected.has(opt.id)}
                  onChange={() => onToggle(opt.id)}
                />
                <span className="truncate" title={opt.name}>
                  {opt.name}
                </span>
              </label>
            ))
          )}
        </div>
      )}
    </div>
  );
}
