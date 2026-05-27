import type {
  ProjectLaborDetail,
  ProjectOperationalFixed,
  ProjectSystemCost,
  ProjectVehicle,
} from "@/services/projectStructure";
import { compareText } from "@/utils/sortComparators";
import type { SortColumnDef } from "@/utils/sortTableRows";

export type ProjectLaborSortColumn = "name" | "type" | "percent" | "cost";

export const PROJECT_LABOR_SORT_COLUMNS: Record<ProjectLaborSortColumn, SortColumnDef<ProjectLaborDetail>> = {
  name: { kind: "text", getValue: (r) => r.name },
  type: { kind: "text", getValue: (r) => r.tipo },
  percent: { kind: "number", getValue: (r) => r.allocation_percentage },
  cost: { kind: "money", getValue: (r) => r.allocated_cost },
};

export function defaultProjectLaborSort(a: ProjectLaborDetail, b: ProjectLaborDetail): number {
  return compareText(a.name, b.name);
}

export type ProjectVehicleSortColumn = "plate" | "model" | "driver" | "km" | "fuel" | "cost";

export const PROJECT_VEHICLE_SORT_COLUMNS: Record<ProjectVehicleSortColumn, SortColumnDef<ProjectVehicle>> = {
  plate: { kind: "text", getValue: (r) => r.plate ?? "" },
  model: { kind: "text", getValue: (r) => r.model ?? "" },
  driver: { kind: "text", getValue: (r) => r.driver_name ?? "" },
  km: { kind: "number", getValue: (r) => r.km_per_month ?? 0 },
  fuel: { kind: "money", getValue: (r) => r.display_fuel_cost ?? r.fuel_cost_realized ?? 0 },
  cost: { kind: "money", getValue: (r) => r.monthly_cost },
};

export function defaultProjectVehicleSort(a: ProjectVehicle, b: ProjectVehicle): number {
  return compareText(a.plate ?? "", b.plate ?? "");
}

export type NamedValueSortColumn = "name" | "value";

export const NAMED_VALUE_SORT_COLUMNS: Record<
  NamedValueSortColumn,
  SortColumnDef<ProjectSystemCost | ProjectOperationalFixed>
> = {
  name: { kind: "text", getValue: (r) => r.name },
  value: { kind: "money", getValue: (r) => r.value },
};

export function defaultNamedValueSort(
  a: ProjectSystemCost | ProjectOperationalFixed,
  b: ProjectSystemCost | ProjectOperationalFixed,
): number {
  return compareText(a.name, b.name);
}
