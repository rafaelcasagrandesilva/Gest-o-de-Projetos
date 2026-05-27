import type { CompanyFinancialItem, TipoFinanceiro } from "@/services/companyFinance";
import type { Project } from "@/services/projects";
import { costCenterLabelFromRef, itemCostCenterRef } from "@/components/company-finance/costCenter";

function normalizeSearchText(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{M}/gu, "");
}

/** Filtro local: nome, descrição, categoria e centro de custo (sem chamada à API). */
export function itemMatchesSearch(
  item: CompanyFinancialItem,
  query: string,
  projects: Project[],
  tipo: TipoFinanceiro,
): boolean {
  const q = normalizeSearchText(query);
  if (!q) return true;

  const ccRef = itemCostCenterRef(item, tipo, projects);
  const ccLabel = costCenterLabelFromRef(ccRef, projects);

  const haystack = [
    item.nome,
    item.description ?? "",
    item.category ?? "",
    item.cost_center ?? "",
    ccLabel,
    item.employee_name ?? "",
  ]
    .map(normalizeSearchText)
    .filter(Boolean);

  return haystack.some((field) => field.includes(q));
}
