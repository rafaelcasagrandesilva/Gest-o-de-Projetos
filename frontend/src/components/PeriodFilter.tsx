export type PeriodMode = "MONTH" | "ALL";

export function PeriodFilter({
  label = "Período",
  mode,
  value,
  onModeChange,
  onChange,
  disabled,
}: {
  label?: string;
  mode: PeriodMode;
  value: string;
  onModeChange: (mode: PeriodMode) => void;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium text-slate-700">{label}</span>
      <div className="flex items-center gap-2">
        <select
          value={mode}
          onChange={(e) => onModeChange(e.target.value as PeriodMode)}
          disabled={disabled}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm disabled:opacity-60"
        >
          <option value="MONTH">Mês</option>
          <option value="ALL">Todos</option>
        </select>
        <input
          type="month"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled || mode === "ALL"}
          className="rounded-lg border border-slate-300 px-3 py-2 disabled:opacity-60"
        />
      </div>
    </label>
  );
}

