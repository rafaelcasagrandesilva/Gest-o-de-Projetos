import type { CompanyFinancialItem, TipoFinanceiro } from "@/services/companyFinance";
import type { Project } from "@/services/projects";
import { matchesSearchWords } from "@/utils/textSearch";
import { costCenterLabelFromRef, itemCostCenterRef } from "@/components/company-finance/costCenter";


/** Filtro local: nome, descrição, categoria e centro de custo (sem chamada à API). */
export function itemMatchesSearch(
  item: CompanyFinancialItem,
  query: string,
  projects: Project[],
  tipo: TipoFinanceiro,
): boolean {
  if (!query.trim()) return true;

  const ccRef = itemCostCenterRef(item, tipo, projects);
  const ccLabel = costCenterLabelFromRef(ccRef, projects);

  return matchesSearchWords(
    [
      item.nome,
      item.item_description,
      item.description,
      item.category,
      item.cost_center,
      ccLabel,
      item.employee_name,
    ],
    query,
  );
}
