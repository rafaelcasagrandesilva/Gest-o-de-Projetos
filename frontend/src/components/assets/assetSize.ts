import { macroCategorySupportsSize, normalizeMacroCategory } from "@/components/assets/assetCategories";

/** Tamanhos sugeridos para EPIs e vestimentas. */
export const SIZE_SUGGESTIONS = [
  "PP",
  "P",
  "M",
  "G",
  "GG",
  "EG",
  "XG",
  "Único",
  "36",
  "37",
  "38",
  "39",
  "40",
  "41",
  "42",
  "43",
  "44",
  "45",
] as const;

export function assetSupportsSize(category: string): boolean {
  return macroCategorySupportsSize(category);
}

export function formatAssetCategoryLine(
  category: string,
  subcategory: string | null | undefined,
  size: string | null | undefined,
): { primary: string; secondary: string | null } {
  const primary = normalizeMacroCategory(category);
  const legacy = (subcategory ?? "").trim();
  const sizeLabel = (size ?? "").trim();
  if (sizeLabel) {
    return { primary, secondary: sizeLabel };
  }
  if (legacy) {
    return { primary, secondary: `Legado: ${legacy}` };
  }
  return { primary, secondary: null };
}
