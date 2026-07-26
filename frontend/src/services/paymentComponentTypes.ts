import { api } from "./api";

export interface PaymentComponentType {
  id: string;
  created_at: string;
  updated_at: string;
  name: string;
  code: string;
  description: string | null;
  is_active: boolean;
  display_order: number;
  usage_count: number;
}

export interface PaymentComponentTypeUpsert {
  name?: string;
  code?: string;
  description?: string | null;
  is_active?: boolean;
  display_order?: number;
}

export async function fetchPaymentComponentTypes(onlyActive = false): Promise<PaymentComponentType[]> {
  const { data } = await api.get<PaymentComponentType[]>("/settings/payment-component-types", {
    params: { only_active: onlyActive },
  });
  return data;
}

export async function createPaymentComponentType(
  payload: PaymentComponentTypeUpsert,
): Promise<PaymentComponentType> {
  const { data } = await api.post<PaymentComponentType>("/settings/payment-component-types", payload);
  return data;
}

export async function updatePaymentComponentType(
  id: string,
  payload: PaymentComponentTypeUpsert,
): Promise<PaymentComponentType> {
  const { data } = await api.patch<PaymentComponentType>(`/settings/payment-component-types/${id}`, payload);
  return data;
}

export async function deletePaymentComponentType(id: string): Promise<void> {
  await api.delete(`/settings/payment-component-types/${id}`);
}
