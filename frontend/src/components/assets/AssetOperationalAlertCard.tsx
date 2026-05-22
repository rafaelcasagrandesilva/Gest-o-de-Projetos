import { Link } from "react-router-dom";
import { formatBRL } from "@/components/assets/assetLabels";

export type OperationalAlertTone = "red" | "amber" | "slate";

type Props = {
  title: string;
  count: number;
  amountTotal: number;
  tone: OperationalAlertTone;
  viewHref: string;
  emptyLabel?: string;
  badge?: string;
  extraLine?: string;
};

const TONE_STYLES: Record<
  OperationalAlertTone,
  { border: string; bg: string; accent: string; badge: string }
> = {
  red: {
    border: "border-red-200",
    bg: "bg-red-50/50",
    accent: "text-red-800",
    badge: "bg-red-100 text-red-800",
  },
  amber: {
    border: "border-amber-200",
    bg: "bg-amber-50/50",
    accent: "text-amber-900",
    badge: "bg-amber-100 text-amber-900",
  },
  slate: {
    border: "border-slate-200",
    bg: "bg-slate-50/50",
    accent: "text-slate-800",
    badge: "bg-slate-100 text-slate-700",
  },
};

export function AssetOperationalAlertCard({
  title,
  count,
  amountTotal,
  tone,
  viewHref,
  emptyLabel = "Nenhum ativo nesta condição.",
  badge,
  extraLine,
}: Props) {
  const styles = TONE_STYLES[tone];
  const hasItems = count > 0;

  return (
    <div className={`flex flex-col rounded-xl border ${styles.border} ${styles.bg} p-4 shadow-sm`}>
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
        {badge ? (
          <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${styles.badge}`}>
            {badge}
          </span>
        ) : null}
      </div>

      {hasItems ? (
        <>
          <p className={`mt-3 text-3xl font-semibold tabular-nums ${styles.accent}`}>{count}</p>
          <p className="mt-1 text-xs text-slate-500">
            {count === 1 ? "ativo impactado" : "ativos impactados"}
          </p>
          <p className="mt-2 text-sm font-medium tabular-nums text-slate-800">{formatBRL(amountTotal)}</p>
          {extraLine ? <p className="mt-1 text-xs text-slate-600">{extraLine}</p> : null}
          <Link
            to={viewHref}
            className="mt-4 inline-flex text-sm font-medium text-indigo-600 hover:text-indigo-800 hover:underline"
          >
            Ver ativos →
          </Link>
        </>
      ) : (
        <p className="mt-3 flex-1 text-sm text-slate-500">{emptyLabel}</p>
      )}
    </div>
  );
}
