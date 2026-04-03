import { api } from "./api";

export interface Revenue {
  id: string;
  created_at: string;
  updated_at: string;
  project_id: string;
  competencia: string;
  amount: number;
  description: string | null;
  status: string;
  has_retention: boolean;
  retention_value: number;
}

export interface RevenueCreate {
  project_id: string;
  competencia: string;
  amount: number;
  description?: string | null;
  status?: "previsto" | "recebido";
  has_retention?: boolean;
}

export async function listRevenues(projectId?: string): Promise<Revenue[]> {
  const { data } = await api.get<Revenue[]>("/financial/revenues", {
    params: projectId ? { project_id: projectId } : undefined,
  });
  return data;
}

export async function createRevenue(payload: RevenueCreate): Promise<Revenue> {
  const { data } = await api.post<Revenue>("/financial/revenues", payload);
  return data;
}

export async function updateRevenue(
  id: string,
  payload: Partial<{
    amount: number;
    description: string | null;
    competencia: string;
    status: "previsto" | "recebido";
    has_retention: boolean;
  }>
): Promise<Revenue> {
  const { data } = await api.patch<Revenue>(`/financial/revenues/${id}`, payload);
  return data;
}

export async function deleteRevenue(id: string): Promise<void> {
  await api.delete(`/financial/revenues/${id}`);
}
