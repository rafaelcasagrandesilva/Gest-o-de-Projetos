import { ASSET_STATUS_LABELS } from "@/components/assets/assetLabels";
import type { AssetStatus } from "@/services/assets";

const STYLES: Record<AssetStatus, string> = {
  AVAILABLE: "bg-emerald-100 text-emerald-800",
  IN_USE: "bg-indigo-100 text-indigo-800",
  MAINTENANCE: "bg-amber-100 text-amber-900",
  EXPIRED: "bg-red-100 text-red-900",
  LOST: "bg-slate-200 text-slate-800",
  DISCARDED: "bg-slate-100 text-slate-600",
};

export function AssetStatusBadge({ status }: { status: AssetStatus }) {
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STYLES[status]}`}>
      {ASSET_STATUS_LABELS[status]}
    </span>
  );
}
