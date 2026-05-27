import type { UserRow } from "@/services/users";
import { compareText } from "@/utils/sortComparators";
import type { SortColumnDef } from "@/utils/sortTableRows";

export type UserSortColumn = "name" | "email" | "role" | "permissions" | "projects" | "active";

export const USER_SORT_COLUMNS: Record<UserSortColumn, SortColumnDef<UserRow>> = {
  name: { kind: "text", getValue: (u) => u.full_name },
  email: { kind: "text", getValue: (u) => u.email },
  role: { kind: "text", getValue: (u) => u.role_names?.[0] ?? "" },
  permissions: { kind: "number", getValue: (u) => u.permission_names?.length ?? 0 },
  projects: { kind: "number", getValue: (u) => u.project_ids?.length ?? 0 },
  active: { kind: "boolean", getValue: (u) => Boolean(u.is_active && !u.deleted_at) },
};

export function defaultUserSort(a: UserRow, b: UserRow): number {
  return compareText(a.full_name, b.full_name);
}
