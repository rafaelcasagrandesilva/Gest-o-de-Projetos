import {
  applyDirection,
  compareByKind,
  type ColumnSortState,
  type SortKind,
  type SortValue,
} from "@/utils/sortComparators";

export type SortColumnDef<T> = {
  kind: SortKind;
  getValue: (row: T) => SortValue;
  statusOrder?: Record<string, number>;
};

/** Ordena cópia de `rows` conforme estado de coluna ou `defaultCompare`. */
export function sortTableRows<T, C extends string>(
  rows: T[],
  sort: ColumnSortState<C>,
  columns: Record<C, SortColumnDef<T>>,
  defaultCompare?: (a: T, b: T) => number,
): T[] {
  const list = [...rows];
  if (!sort.column) {
    if (defaultCompare) list.sort(defaultCompare);
    return list;
  }
  const def = columns[sort.column];
  if (!def) return list;
  list.sort((a, b) => {
    const cmp = compareByKind(def.getValue(a), def.getValue(b), def.kind, def.statusOrder);
    return applyDirection(cmp, sort.direction);
  });
  return list;
}
