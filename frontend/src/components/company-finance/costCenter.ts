import type { CompanyFinancialItem, TipoFinanceiro } from "@/services/companyFinance";
import type { Project } from "@/services/projects";

export const CC_REF_ADMINISTRATIVO = "ADMINISTRATIVO";
export const CC_REF_FINANCEIRO = "FINANCEIRO";
export const CC_REF_RH = "RH";
export const CC_REF_ALMOXARIFADO = "ALMOXARIFADO";

export const CC_FIXED_OPTIONS: { ref: string; label: string }[] = [
  { ref: CC_REF_ADMINISTRATIVO, label: "Administrativo" },
  { ref: CC_REF_FINANCEIRO, label: "Financeiro" },
  { ref: CC_REF_ALMOXARIFADO, label: "Almoxarifado" },
  { ref: CC_REF_RH, label: "RH" },
];

export function defaultCostCenterRef(tipo: TipoFinanceiro): string {
  return tipo === "endividamento" ? CC_REF_FINANCEIRO : CC_REF_ADMINISTRATIVO;
}

export function isSystemCostCenterRef(ref: string): boolean {
  return (
    ref === CC_REF_ADMINISTRATIVO ||
    ref === CC_REF_FINANCEIRO ||
    ref === CC_REF_ALMOXARIFADO ||
    ref === CC_REF_RH
  );
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
  if (ref === CC_REF_ALMOXARIFADO) return "Almoxarifado";
  if (ref === CC_REF_RH) return "RH";
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
    if (legacyKey === "almoxarifado" || legacyKey === "almox") return CC_REF_ALMOXARIFADO;
    if (legacyKey === "rh" || legacyKey === "recursos humanos") return CC_REF_RH;
    const byName = projects.find((p: Project) => normalizeLabelKey(p.name) === legacyKey);
    if (byName) return byName.id;
  }
  const sys = item.cost_center_system;
  if (
    sys === CC_REF_ADMINISTRATIVO ||
    sys === CC_REF_FINANCEIRO ||
    sys === CC_REF_ALMOXARIFADO ||
    sys === CC_REF_RH
  ) {
    return sys;
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
