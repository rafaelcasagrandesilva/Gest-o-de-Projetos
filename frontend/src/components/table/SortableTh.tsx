import type { TableSortHeaderProps } from "@/hooks/useTableSort";

type SortableThProps = TableSortHeaderProps & {
  label: string;
  column: string;
  className?: string;
  align?: "left" | "right";
  /** finance = cabeçalho compacto uppercase (módulos financeiros). */
  variant?: "finance" | "standard";
};

export function SortableTh({
  label,
  column,
  activeColumn,
  direction,
  onSort,
  className = "",
  align = "left",
  variant = "finance",
}: SortableThProps) {
  const active = activeColumn === column;
  const indicator = !active ? "↕" : direction === "asc" ? "↑" : "↓";

  const thBase =
    variant === "finance"
      ? `px-2 py-3 text-xs font-semibold uppercase tracking-wide ${align === "right" ? "text-right" : "text-left"}`
      : `px-4 py-3 font-medium text-slate-600 ${align === "right" ? "text-right" : "text-left"}`;

  const btnBase =
    variant === "finance"
      ? "group inline-flex max-w-full items-center gap-1"
      : "group inline-flex max-w-full items-center gap-1.5";

  return (
    <th className={`${thBase} ${className}`} aria-sort={active ? (direction === "asc" ? "ascending" : "descending") : "none"}>
      <button
        type="button"
        onClick={() => onSort(column)}
        className={`${btnBase} ${align === "right" ? "ml-auto flex-row-reverse" : ""} ${
          active ? "text-indigo-700" : variant === "finance" ? "text-slate-600 hover:text-slate-900" : "text-slate-600 hover:text-slate-900"
        }`}
      >
        <span className="truncate">{label}</span>
        <span
          className={`shrink-0 text-[10px] leading-none tabular-nums ${
            active ? "text-indigo-600" : "text-slate-400 opacity-60 group-hover:opacity-100"
          }`}
          aria-hidden
        >
          {indicator}
        </span>
      </button>
    </th>
  );
}
