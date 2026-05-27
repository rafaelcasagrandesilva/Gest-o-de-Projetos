import type { AssetListItem } from "@/services/assets";
import { compareText } from "@/utils/sortComparators";
import type { SortColumnDef } from "@/utils/sortTableRows";

export type AssetSortColumn =
  | "code"
  | "name"
  | "category"
  | "holder"
  | "cost_center"
  | "value";

export const ASSET_SORT_COLUMNS: Record<AssetSortColumn, SortColumnDef<AssetListItem>> = {
  code: { kind: "text", getValue: (r) => r.asset_code },
  name: { kind: "text", getValue: (r) => r.name },
  category: { kind: "text", getValue: (r) => `${r.category} ${r.subcategory ?? ""}` },
  holder: { kind: "text", getValue: (r) => r.current_holder_name ?? "" },
  cost_center: { kind: "text", getValue: (r) => r.cost_center_label ?? "" },
  value: { kind: "money", getValue: (r) => r.purchase_value ?? 0 },
};

export function defaultAssetSort(a: AssetListItem, b: AssetListItem): number {
  return compareText(a.asset_code, b.asset_code);
}
