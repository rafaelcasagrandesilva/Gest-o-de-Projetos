/** Badge de status financeiro — tons corporativos discretos, compartilhado entre módulos. */

export type StatusTone = "green" | "amber" | "red" | "blue" | "slate";

const TONE_CLASS: Record<StatusTone, string> = {
  green: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
  amber: "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
  red: "bg-rose-50 text-rose-700 ring-1 ring-rose-200",
  blue: "bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200",
  slate: "bg-slate-100 text-slate-600 ring-1 ring-slate-200",
};

export function StatusBadge({ label, tone }: { label: string; tone: StatusTone }) {
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${TONE_CLASS[tone]}`}>
      {label}
    </span>
  );
}
