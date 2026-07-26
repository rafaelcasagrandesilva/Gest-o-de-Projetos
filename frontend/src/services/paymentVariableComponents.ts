import { api } from "./api";

export interface PaymentVariableComponent {
  id: string;
  created_at: string;
  updated_at: string;
  type_id: string;
  type_name: string;
  type_code: string;
  employee_id: string;
  competencia: string;
  amount: number;
  note: string | null;
  project_labor_id: string | null;
  company_financial_item_id: string | null;
}

/** Item enviado no salvamento em lote (sem id = novo). */
export interface VariableComponentItem {
  id?: string;
  type_id: string;
  amount: number;
  note?: string | null;
}

export async function fetchProjectLaborComponents(
  laborId: string,
): Promise<PaymentVariableComponent[]> {
  const { data } = await api.get<PaymentVariableComponent[]>("/payment-variable-components", {
    params: { project_labor_id: laborId },
  });
  return data;
}

/** Persiste TODO o conjunto de componentes do vínculo numa única operação (transação única). */
export async function replaceProjectLaborComponents(
  laborId: string,
  items: VariableComponentItem[],
): Promise<PaymentVariableComponent[]> {
  const { data } = await api.put<PaymentVariableComponent[]>(
    `/payment-variable-components/project-labor/${laborId}`,
    { items },
  );
  return data;
}

export async function fetchCompanyItemComponents(
  itemId: string,
  competencia: string,
): Promise<PaymentVariableComponent[]> {
  const { data } = await api.get<PaymentVariableComponent[]>("/payment-variable-components", {
    params: { company_financial_item_id: itemId, competencia },
  });
  return data;
}

/** Persiste os componentes do item de Custo Fixo na competência (transação única). */
export async function replaceCompanyItemComponents(
  itemId: string,
  competencia: string,
  items: VariableComponentItem[],
): Promise<PaymentVariableComponent[]> {
  const { data } = await api.put<PaymentVariableComponent[]>(
    `/payment-variable-components/company-item/${itemId}`,
    { items },
    { params: { competencia } },
  );
  return data;
}
