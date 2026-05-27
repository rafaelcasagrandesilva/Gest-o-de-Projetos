export const EPI_MACRO_CATEGORY = "EPI";

/** Todas as categorias (inclui EPI). */
export const ASSET_MACRO_CATEGORIES = [
  "Tecnologia",
  "EPI",
  "EPC",
  "Ferramenta",
  "Operacional",
  "Instrumentação",
  "Veículos",
  "Uniformes",
] as const;

/** Categorias do módulo patrimonial (sem EPI). */
export const PATRIMONIAL_MACRO_CATEGORIES = ASSET_MACRO_CATEGORIES.filter((c) => c !== EPI_MACRO_CATEGORY);

const LEGACY_MAP: Record<string, string> = {
  TECNOLOGIA: "Tecnologia",
  EPIS: "EPI",
  EPI: "EPI",
  FERRAMENTAS: "Ferramenta",
  FERRAMENTA: "Ferramenta",
  OPERACIONAL: "Operacional",
  INSTRUMENTACAO: "Instrumentação",
  INSTRUMENTAÇÃO: "Instrumentação",
  VEICULOS: "Veículos",
  VEÍCULOS: "Veículos",
  UNIFORMES: "Uniformes",
};

export function normalizeMacroCategory(category: string): string {
  const raw = category.trim();
  if (!raw) return "Operacional";
  const mapped = LEGACY_MAP[raw.toUpperCase()];
  if (mapped) return mapped;
  const hit = ASSET_MACRO_CATEGORIES.find((c) => c.toLowerCase() === raw.toLowerCase());
  return hit ?? raw;
}

export function macroCategorySupportsSize(category: string): boolean {
  const norm = normalizeMacroCategory(category);
  return norm === "EPI" || norm === "EPC" || norm === "Uniformes";
}

export function isEpiMacroCategory(category: string): boolean {
  const norm = normalizeMacroCategory(category);
  return norm === "EPI" || norm === "EPC";
}

export function isTechMacroCategory(category: string): boolean {
  return normalizeMacroCategory(category) === "Tecnologia";
}
