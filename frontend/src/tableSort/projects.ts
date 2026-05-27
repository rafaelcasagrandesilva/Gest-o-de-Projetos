import type { Project } from "@/services/projects";
import { compareText } from "@/utils/sortComparators";
import type { SortColumnDef } from "@/utils/sortTableRows";

export type ProjectSortColumn = "name" | "status" | "description";

export const PROJECT_SORT_COLUMNS: Record<ProjectSortColumn, SortColumnDef<Project>> = {
  name: { kind: "text", getValue: (p) => p.name },
  status: { kind: "boolean", getValue: (p) => p.is_active },
  description: { kind: "text", getValue: (p) => p.description ?? "" },
};

export function defaultProjectSort(a: Project, b: Project): number {
  return compareText(a.name, b.name);
}
