import { PHYSICAL_CONDITION_LABELS } from "@/components/assets/assetLabels";
import type { AssetPhysicalCondition } from "@/services/assets";

const STYLES: Record<AssetPhysicalCondition, string> = {
  NEW: "bg-sky-100 text-sky-800",
  GOOD: "bg-teal-100 text-teal-800",
  FAIR: "bg-orange-100 text-orange-900",
  DAMAGED: "bg-red-100 text-red-900",
};

export function AssetPhysicalConditionBadge({
  condition,
}: {
  condition: AssetPhysicalCondition | null | undefined;
}) {
  if (!condition) return <span className="text-xs text-slate-400">—</span>;
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STYLES[condition]}`}>
      {PHYSICAL_CONDITION_LABELS[condition]}
    </span>
  );
}
