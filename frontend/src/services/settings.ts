import { api } from "./api";

export interface SystemSettings {
  id: string;
  created_at: string;
  updated_at: string;
  tax_rate: number;
  overhead_rate: number;
  anticipation_rate: number;
  clt_charges_rate: number;
  vehicle_light_cost: number;
  vehicle_pickup_cost: number;
  vehicle_sedan_cost: number;
  vr_value: number;
  fuel_ethanol: number;
  fuel_gasoline: number;
  fuel_diesel: number;
  consumption_light: number;
  consumption_pickup: number;
  consumption_sedan: number;
}

export async function fetchSettings(): Promise<SystemSettings> {
  const { data } = await api.get<SystemSettings>("/settings/");
  return data;
}

export async function updateSettings(payload: Partial<SystemSettings>): Promise<SystemSettings> {
  const { data } = await api.put<SystemSettings>("/settings/", payload);
  return data;
}
