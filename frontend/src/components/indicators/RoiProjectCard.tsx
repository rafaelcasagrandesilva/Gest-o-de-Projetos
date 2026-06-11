import type { ProjectRoi } from "@/services/indicators";
import { formatCurrency } from "@/utils/currency";
import { formatRoiPct, roiTone } from "@/utils/roiFormat";

/** Card de ROI por projeto (visual executivo). */
export function RoiProjectCard({ item }: { item: ProjectRoi }) {
  const tone = roiTone(item.roi);
  return (
    <div className={`w-full rounded-xl border bg-white p-5 shadow-sm ${tone.card}`}>
      <div className="flex items-start justify-between gap-3">
        <h3 className="min-w-0 truncate text-sm font-semibold text-slate-900" title={item.project_name}>
          {item.project_name}
        </h3>
        <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold ${tone.badge}`}>ROI</span>
      </div>
      <p className={`mt-3 text-3xl font-bold tabular-nums ${tone.text}`}>{formatRoiPct(item.roi_pct)}</p>
      <dl className="mt-4 space-y-1.5 text-sm">
        <div className="flex justify-between">
          <dt className="text-slate-500">Receita</dt>
          <dd className="tabular-nums text-slate-700">{formatCurrency(item.revenue)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-slate-500">Custo</dt>
          <dd className="tabular-nums text-slate-700">{formatCurrency(item.cost)}</dd>
        </div>
        <div className="flex justify-between border-t border-slate-100 pt-1.5">
          <dt className="font-medium text-slate-600">Lucro operacional</dt>
          <dd
            className={`font-semibold tabular-nums ${
              item.operational_profit < 0 ? "text-rose-600" : "text-slate-900"
            }`}
          >
            {formatCurrency(item.operational_profit)}
          </dd>
        </div>
      </dl>
    </div>
  );
}
