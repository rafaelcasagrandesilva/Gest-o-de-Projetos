import type { CompanyFinancialItem, TipoFinanceiro } from "@/services/companyFinance";
import type { Project } from "@/services/projects";

export const CC_REF_ADMINISTRATIVO = "ADMINISTRATIVO";
export const CC_REF_FINANCEIRO = "FINANCEIRO";

export const CC_FIXED_OPTIONS: { ref: string; label: string }[] = [
  { ref: CC_REF_ADMINISTRATIVO, label: "Administrativo" },
  { ref: CC_REF_FINANCEIRO, label: "Financeiro" },
];

export function defaultCostCenterRef(tipo: TipoFinanceiro): string {
  return tipo === "endividamento" ? CC_REF_FINANCEIRO : CC_REF_ADMINISTRATIVO;
}

export function isSystemCostCenterRef(ref: string): boolean {
  return ref === CC_REF_ADMINISTRATIVO || ref === CC_REF_FINANCEIRO;
}

function normalizeLabelKey(label: string): string {
  return label
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .replace(/[–—]/g, "-");
}

export function costCenterLabelFromRef(ref: string, projects: Project[]): string {
  if (ref === CC_REF_ADMINISTRATIVO) return "Administrativo";
  if (ref === CC_REF_FINANCEIRO) return "Financeiro";
  const project = projects.find((p) => p.id === ref);
  if (project) return project.name;
  return ref;
}

export function itemCostCenterRef(item: CompanyFinancialItem, tipo: TipoFinanceiro, projects: Project[] = []): string {
  if (item.cost_center_ref) return item.cost_center_ref;
  if (item.cost_center_project_id) return item.cost_center_project_id;
  const legacy = (item.cost_center ?? "").trim();
  if (legacy) {
    const legacyKey = normalizeLabelKey(legacy);
    if (legacyKey === "administrativo") return CC_REF_ADMINISTRATIVO;
    if (legacyKey === "financeiro") return CC_REF_FINANCEIRO;
    const byName = projects.find((p: Project) => normalizeLabelKey(p.name) === legacyKey);
    if (byName) return byName.id;
  }
  if (item.cost_center_system === CC_REF_ADMINISTRATIVO || item.cost_center_system === CC_REF_FINANCEIRO) {
    return item.cost_center_system;
  }
  return defaultCostCenterRef(tipo);
}

export function mergeProjectsForCostCenter(projects: Project[], selectedRef: string | null | undefined): Project[] {
  if (!selectedRef || isSystemCostCenterRef(selectedRef)) return projects;
  if (projects.some((p) => p.id === selectedRef)) return projects;
  return [
    ...projects,
    {
      id: selectedRef,
      name: `Projeto (legado / inativo)`,
      code: null,
      description: null,
      created_at: "",
      updated_at: "",
      is_active: false,
    },
  ];
}
