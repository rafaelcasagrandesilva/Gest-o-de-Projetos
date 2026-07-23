import { api } from "./api";
import type { Project } from "@/services/projects";

/** Item mínimo de referência de Centro de Custo (id + nome), sem dados financeiros. */
export type CostCenterRef = { ref: string; label: string };

/**
 * Opções de Centro de Custo para SELETORES (Etapa 2). Exige apenas `cost_center.reference` no
 * backend — NÃO `projects.view`. Retorna somente {ref, label} dos projetos ativos (sem contrato/
 * valores/comprador). Os Centros Administrativos fixos são constantes do próprio CostCenterSelect.
 */
export async function listCostCenterRefs(): Promise<CostCenterRef[]> {
  const { data } = await api.get<CostCenterRef[]>("/cost-centers/reference");
  return data;
}

/**
 * Adapta os itens mínimos ao formato `Project` consumido por `CostCenterSelect` (que usa apenas
 * id/name/is_active/closed_at/deleted_at). Campos financeiros ficam ausentes — nunca trafegam.
 */
export function costCenterRefsAsProjects(refs: CostCenterRef[]): Project[] {
  return refs.map((r) => ({
    id: r.ref,
    name: r.label,
    code: null,
    description: null,
    created_at: "",
    updated_at: "",
    is_active: true,
    closed_at: null,
    deleted_at: null,
  }));
}

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
