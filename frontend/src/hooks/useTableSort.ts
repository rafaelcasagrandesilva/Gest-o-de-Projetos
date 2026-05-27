import { useCallback, useMemo, useState } from "react";
import { cycleColumnSort, type ColumnSortState } from "@/utils/sortComparators";
import { sortTableRows, type SortColumnDef } from "@/utils/sortTableRows";

export type TableSortHeaderProps = {
  activeColumn: string | null;
  direction: ColumnSortState<string>["direction"];
  onSort: (column: string) => void;
};

export function useTableSort<T, C extends string>(
  rows: T[],
  columns: Record<C, SortColumnDef<T>>,
  options?: {
    defaultCompare?: (a: T, b: T) => number;
  },
) {
  const [sort, setSort] = useState<ColumnSortState<C>>({ column: null, direction: "asc" });

  const onSort = useCallback((column: string) => {
    setSort((prev) => cycleColumnSort(prev, column as C));
  }, []);

  const sortedRows = useMemo(
    () => sortTableRows(rows, sort, columns, options?.defaultCompare),
    [rows, sort, columns, options?.defaultCompare],
  );

  const headerSort: TableSortHeaderProps = useMemo(
    () => ({
      activeColumn: sort.column,
      direction: sort.direction,
      onSort,
    }),
    [sort.column, sort.direction, onSort],
  );

  return { sort, sortedRows, onSort, headerSort };
}
