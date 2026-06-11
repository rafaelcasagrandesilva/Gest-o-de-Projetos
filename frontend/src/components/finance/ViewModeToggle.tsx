/** Seletor de visão (tabs) — padrão compartilhado entre módulos financeiros. */

export type ViewOption<T extends string> = { value: T; label: string };

export function ViewModeToggle<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: ViewOption<T>[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          aria-pressed={value === opt.value}
          className={`rounded-md px-4 py-1.5 text-sm font-medium transition-colors ${
            value === opt.value ? "bg-indigo-600 text-white shadow-sm" : "text-slate-600 hover:bg-slate-50"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
