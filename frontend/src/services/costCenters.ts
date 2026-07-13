import { api } from "./api";

/**
 * Fonte ÚNICA de Centros de Custo do frontend para os combos de cadastro
 * (Colaboradores, Veículos, Projetos). Bate no endpoint central
 * `GET /collaborators/cost-centers`, que compõe os Centros Administrativos fixos com os
 * Centros de Custo dos projetos ATIVOS. Nenhuma tela deve montar sua própria lista.
 */
export async function fetchCostCenters(): Promise<string[]> {
  const { data } = await api.get<string[]>("/collaborators/cost-centers");
  return data;
}

/**
 * Rótulo de um Centro de Custo já gravado num registro, considerando a lista atual de opções.
 * Se o valor não está mais entre os disponíveis (ex.: projeto encerrado), sufixa "(encerrado)"
 * para deixar claro que é um vínculo legado — mas ele NÃO deve ser oferecido para novos cadastros.
 */
export function costCenterOptionLabel(value: string, available: string[]): string {
  if (!value) return value;
  return available.includes(value) ? value : `${value} (encerrado)`;
}
