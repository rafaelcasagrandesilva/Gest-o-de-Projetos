export type SortDirection = "asc" | "desc";

export type ColumnSortState<T extends string> = {
  column: T | null;
  direction: SortDirection;
};

/** Ciclo: inativo → crescente → decrescente → inativo (padrão da tela). */
export function cycleColumnSort<T extends string>(
  current: ColumnSortState<T>,
  column: T,
): ColumnSortState<T> {
  if (current.column !== column) return { column, direction: "asc" };
  if (current.direction === "asc") return { column, direction: "desc" };
  return { column: null, direction: "asc" };
}

export function applyDirection(cmp: number, direction: SortDirection): number {
  return direction === "asc" ? cmp : -cmp;
}

export function compareText(a: string, b: string): number {
  return a.localeCompare(b, "pt-BR", { sensitivity: "base" });
}

export function compareNumber(a: number, b: number): number {
  if (a === b) return 0;
  return a < b ? -1 : 1;
}

export function compareDateIso(a: string, b: string): number {
  return a.slice(0, 10).localeCompare(b.slice(0, 10));
}

export function compareMoney(a: number, b: number): number {
  return compareNumber(a, b);
}

export function compareBoolean(a: boolean, b: boolean): number {
  return Number(a) - Number(b);
}

/** Nº documento / NF: prioriza dígitos; desempate alfanumérico. */
export function compareDocumentNumber(a: string, b: string): number {
  const na = Number.parseInt(a.replace(/\D/g, ""), 10);
  const nb = Number.parseInt(b.replace(/\D/g, ""), 10);
  const aNum = Number.isFinite(na) ? na : null;
  const bNum = Number.isFinite(nb) ? nb : null;
  if (aNum != null && bNum != null && aNum !== bNum) return aNum - bNum;
  return compareText(a, b);
}

export type SortKind = "text" | "number" | "money" | "date" | "documentNumber" | "status" | "boolean";

export type SortValue = string | number | boolean | null | undefined;

export function compareByKind(
  a: SortValue,
  b: SortValue,
  kind: SortKind,
  statusOrder?: Record<string, number>,
): number {
  if (kind === "boolean") {
    return compareBoolean(Boolean(a), Boolean(b));
  }
  if (kind === "number" || kind === "money") {
    const na = typeof a === "number" && Number.isFinite(a) ? a : 0;
    const nb = typeof b === "number" && Number.isFinite(b) ? b : 0;
    return kind === "money" ? compareMoney(na, nb) : compareNumber(na, nb);
  }
  if (kind === "date") {
    return compareDateIso(String(a ?? ""), String(b ?? ""));
  }
  if (kind === "documentNumber") {
    return compareDocumentNumber(String(a ?? ""), String(b ?? ""));
  }
  if (kind === "status") {
    const sa = String(a ?? "");
    const sb = String(b ?? "");
    const oa = statusOrder?.[sa] ?? 99;
    const ob = statusOrder?.[sb] ?? 99;
    if (oa !== ob) return oa - ob;
    return compareText(sa, sb);
  }
  return compareText(String(a ?? ""), String(b ?? ""));
}
