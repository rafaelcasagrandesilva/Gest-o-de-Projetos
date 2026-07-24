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
  /** Custo fixo mensal (R$) cadastrado no veículo. Redigido (null) sem `vehicles.sensitive`. */
  monthly_cost: number | null;
  driver_employee_id: string | null;
  driver_name: string | null;
  /** Cache do Centro de Custo vigente (fonte da verdade é temporal — histórico). */
  cost_center: string | null;
  /** JSON da API: `active` */
  active: boolean;
  /** Ciclo de vida: entrada (start_date) / saída (end_date). */
  start_date: string | null;
  end_date: string | null;
}

export interface FleetVehicleCreate {
  plate: string;
  model?: string | null;
  description?: string | null;
  vehicle_type?: FleetVehicleType;
  monthly_cost: number;
  driver_employee_id?: string | null;
  cost_center?: string | null;
  is_active?: boolean;
  /** Ciclo de vida — entrada obrigatória em novos cadastros; saída opcional. */
  start_date: string;
  end_date?: string | null;
}

export interface FleetVehicleUpdate {
  plate?: string;
  model?: string | null;
  description?: string | null;
  vehicle_type?: FleetVehicleType;
  monthly_cost?: number;
  driver_employee_id?: string | null;
  cost_center?: string | null;
  /** Competência a partir da qual o novo Centro de Custo vale (histórico). Ausente = atual. */
  cost_center_effective_date?: string | null;
  is_active?: boolean;
  start_date?: string | null;
  end_date?: string | null;
}

export async function listFleetVehicles(options?: {
  /** Incluir inativos (admin). Deletados nunca retornam. */
  include_inactive?: boolean;
  /** LEGADO: quando true, equivale a listFleetVehiclesActive(). */
  active_only?: boolean;
  offset?: number;
  limit?: number;
  /** Filtra a frota por Centro de Custo (igualdade estrita). Omitido/"" = todos. */
  cost_center?: string;
}): Promise<FleetVehicle[]> {
  if (options?.active_only) {
    return await listFleetVehiclesActive({ offset: options?.offset, limit: options?.limit });
  }
  const cc = (options?.cost_center ?? "").trim();
  const { data } = await api.get<FleetVehicle[]>("/vehicles/", {
    params: {
      include_inactive: options?.include_inactive ?? false,
      offset: options?.offset ?? 0,
      limit: options?.limit ?? 200,
      ...(cc ? { cost_center: cc } : {}),
    },
  });
  return data;
}

export async function listFleetVehiclesActive(options?: {
  offset?: number;
  limit?: number;
  /** Filtra por Centro de Custo do projeto (aba Veículos), resolvido por competência. */
  project_id?: string;
  /** Competência (YYYY-MM-01) para resolver o Centro de Custo vigente do veículo. */
  competencia?: string;
}): Promise<FleetVehicle[]> {
  const { data } = await api.get<FleetVehicle[]>("/vehicles/active", {
    params: {
      offset: options?.offset ?? 0,
      limit: options?.limit ?? 200,
      ...(options?.project_id ? { project_id: options.project_id } : {}),
      ...(options?.competencia ? { competencia: options.competencia } : {}),
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
