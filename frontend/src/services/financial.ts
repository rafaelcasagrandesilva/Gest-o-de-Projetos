import { api } from "./api";

const DEFAULT_SCENARIO_QUERY = "REALIZADO";

export interface Revenue {
  id: string;
  created_at: string;
  updated_at: string;
  project_id: string;
  competencia: string;
  scenario?: string;
  // `null` quando redigido por falta de "Dados sensíveis" (billing.sensitive).
  amount: number | null;
  description: string | null;
  status: string;
  has_retention: boolean;
  retention_value: number | null;
  /** Fonte do valor NESTA competência: false = valor manual, true = soma das NFs faturadas. */
  use_nf_amount: boolean;
  /** Soma do BRUTO das NFs FATURADAS da mesma competência (pré-faturada e cancelada fora).
   *  `null` = sem NF no mês, ou redigido por falta de "Dados sensíveis". */
  nf_amount: number | null;
  /** O valor que o Dashboard realmente usa: manual ou soma das NFs, conforme a marcação. */
  effective_amount: number | null;
}

export interface RevenueCreate {
  project_id: string;
  competencia: string;
  amount: number;
  description?: string | null;
  status?: "previsto" | "recebido";
  has_retention?: boolean;
  scenario?: string;
}

export async function listRevenues(projectId?: string, scenario?: string): Promise<Revenue[]> {
  const params: Record<string, string> = { scenario: scenario ?? DEFAULT_SCENARIO_QUERY };
  if (projectId) params.project_id = projectId;
  const { data } = await api.get<Revenue[]>("/financial/revenues/", { params });
  return data;
}

export async function createRevenue(payload: RevenueCreate): Promise<Revenue> {
  const { data } = await api.post<Revenue>("/financial/revenues/", payload);
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
    use_nf_amount: boolean;
  }>
): Promise<Revenue> {
  const { data } = await api.patch<Revenue>(`/financial/revenues/${id}/`, payload);
  return data;
}

export async function deleteRevenue(id: string): Promise<void> {
  await api.delete(`/financial/revenues/${id}/`);
}
