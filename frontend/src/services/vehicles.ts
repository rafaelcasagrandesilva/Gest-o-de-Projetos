import { api } from "./api";

export type FleetVehicleType = "LIGHT" | "PICKUP" | "SEDAN";

export interface FleetVehicle {
  id: string;
  created_at: string;
  updated_at: string;
  plate: string;
  model: string | null;
  description: string | null;
  /** Categoria (LIGHT, PICKUP, SEDAN); JSON da API: `type` */
  type: string;
  /** Custo fixo mensal (R$) cadastrado no veículo */
  monthly_cost: number;
  driver_employee_id: string | null;
  driver_name: string | null;
  /** JSON da API: `active` */
  active: boolean;
}

export interface FleetVehicleCreate {
  plate: string;
  model?: string | null;
  description?: string | null;
  vehicle_type?: FleetVehicleType;
  monthly_cost: number;
  driver_employee_id?: string | null;
  is_active?: boolean;
}

export interface FleetVehicleUpdate {
  plate?: string;
  model?: string | null;
  description?: string | null;
  vehicle_type?: FleetVehicleType;
  monthly_cost?: number;
  driver_employee_id?: string | null;
  is_active?: boolean;
}

export async function listFleetVehicles(options?: {
  /** Incluir inativos (admin). Deletados nunca retornam. */
  include_inactive?: boolean;
  /** LEGADO: quando true, equivale a listFleetVehiclesActive(). */
  active_only?: boolean;
  offset?: number;
  limit?: number;
}): Promise<FleetVehicle[]> {
  if (options?.active_only) {
    return await listFleetVehiclesActive({ offset: options?.offset, limit: options?.limit });
  }
  const { data } = await api.get<FleetVehicle[]>("/vehicles/", {
    params: {
      include_inactive: options?.include_inactive ?? false,
      offset: options?.offset ?? 0,
      limit: options?.limit ?? 200,
    },
  });
  return data;
}

export async function listFleetVehiclesActive(options?: { offset?: number; limit?: number }): Promise<FleetVehicle[]> {
  const { data } = await api.get<FleetVehicle[]>("/vehicles/active", {
    params: {
      offset: options?.offset ?? 0,
      limit: options?.limit ?? 200,
    },
  });
  return data;
}

export async function createFleetVehicle(body: FleetVehicleCreate): Promise<FleetVehicle> {
  const { data } = await api.post<FleetVehicle>("/vehicles/", body);
  return data;
}

export async function updateFleetVehicle(id: string, body: FleetVehicleUpdate): Promise<FleetVehicle> {
  const { data } = await api.patch<FleetVehicle>(`/vehicles/${id}/`, body);
  return data;
}

export async function deleteFleetVehicle(id: string): Promise<void> {
  await api.delete(`/vehicles/${id}/`);
}
