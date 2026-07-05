import { api } from "./api";

/** Perfis de operação suportados (cada um tem seu Operation Handler no backend). */
export type OperationProfile = "LEPTA" | "DAYCOVAL";

export const OPERATION_PROFILE_OPTIONS: { value: OperationProfile; label: string }[] = [
  { value: "LEPTA", label: "Lepta (basis por NF + repasse 7%)" },
  { value: "DAYCOVAL", label: "Daycoval (valor antecipado por NF + liquidação)" },
];

export interface AdvanceInstitution {
  id: string;
  name: string;
  institution_type: string;
  operation_profile: OperationProfile;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export async function fetchAdvanceInstitutions(params?: { only_active?: boolean }): Promise<AdvanceInstitution[]> {
  const { data } = await api.get<AdvanceInstitution[]>("/invoices/advance-institutions", { params });
  return data;
}

export async function createAdvanceInstitution(payload: {
  name: string;
  institution_type: string;
  operation_profile: OperationProfile;
  is_active?: boolean;
}): Promise<AdvanceInstitution> {
  const { data } = await api.post<AdvanceInstitution>("/invoices/advance-institutions", payload);
  return data;
}

export async function updateAdvanceInstitution(
  id: string,
  payload: Partial<{
    name: string;
    institution_type: string;
    operation_profile: OperationProfile;
    is_active: boolean;
  }>,
): Promise<AdvanceInstitution> {
  const { data } = await api.patch<AdvanceInstitution>(`/invoices/advance-institutions/${id}`, payload);
  return data;
}

export async function deleteAdvanceInstitution(id: string): Promise<void> {
  await api.delete(`/invoices/advance-institutions/${id}`);
}
