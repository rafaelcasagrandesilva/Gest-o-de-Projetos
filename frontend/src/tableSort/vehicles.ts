import type { FleetVehicle } from "@/services/vehicles";
import { compareText } from "@/utils/sortComparators";
import type { SortColumnDef } from "@/utils/sortTableRows";

export type FleetVehicleSortColumn =
  | "plate"
  | "model"
  | "type"
  | "monthly_cost"
  | "driver"
  | "active";

export function fleetTypeLabel(t: string): string {
  switch (t) {
    case "LIGHT":
      return "Leve";
    case "PICKUP":
      return "Pickup";
    case "SEDAN":
      return "Sedan";
    default:
      return t;
  }
}

export const FLEET_VEHICLE_SORT_COLUMNS: Record<FleetVehicleSortColumn, SortColumnDef<FleetVehicle>> = {
  plate: { kind: "text", getValue: (v) => v.plate },
  model: { kind: "text", getValue: (v) => v.model ?? "" },
  type: { kind: "text", getValue: (v) => fleetTypeLabel(v.type) },
  monthly_cost: { kind: "money", getValue: (v) => v.monthly_cost },
  driver: { kind: "text", getValue: (v) => v.driver_name ?? "" },
  active: { kind: "boolean", getValue: (v) => v.active },
};

export function defaultFleetVehicleSort(a: FleetVehicle, b: FleetVehicle): number {
  return compareText(a.plate, b.plate);
}
