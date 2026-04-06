/** Espelha `app/core/permission_codes.ALL_PERMISSION_CODES` (ordem estável para UI). */
export const ALL_PERMISSION_CODES: string[] = [
  "system.admin",
  "system.all_projects",
  "dashboard.view",
  "dashboard.director",
  "projects.view",
  "projects.create",
  "projects.edit",
  "projects.delete",
  "employees.view",
  "employees.edit",
  "vehicles.view",
  "vehicles.edit",
  "billing.view",
  "invoices.view",
  "invoices.edit",
  "debts.view",
  "debts.edit",
  "costs.view",
  "costs.edit",
  "settings.view",
  "settings.edit",
  "users.manage",
  "reports.view",
  "reports.export",
  "alerts.view",
  "company_finance.view",
  "company_finance.edit",
];

export const PERMISSION_LABELS: Record<string, string> = {
  "system.admin": "Administração total",
  "system.all_projects": "Ver todos os projetos",
  "dashboard.view": "Dashboard (visualizar)",
  "dashboard.director": "Dashboard diretoria",
  "projects.view": "Projetos (visualizar)",
  "projects.create": "Projetos (criar)",
  "projects.edit": "Projetos (editar)",
  "projects.delete": "Projetos (excluir)",
  "employees.view": "Colaboradores (visualizar)",
  "employees.edit": "Colaboradores (editar)",
  "vehicles.view": "Veículos (visualizar)",
  "vehicles.edit": "Veículos (editar)",
  "billing.view": "Faturamento",
  "invoices.view": "Notas fiscais (visualizar)",
  "invoices.edit": "Notas fiscais (editar)",
  "debts.view": "Endividamento (visualizar)",
  "debts.edit": "Endividamento (editar)",
  "costs.view": "Custos (visualizar)",
  "costs.edit": "Custos (editar)",
  "settings.view": "Configurações (visualizar)",
  "settings.edit": "Configurações (editar)",
  "users.manage": "Gerenciar usuários",
  "reports.view": "Relatórios (visualizar)",
  "reports.export": "Relatórios (exportar)",
  "alerts.view": "Alertas",
  "company_finance.view": "Finanças empresa (visualizar)",
  "company_finance.edit": "Finanças empresa (editar)",
};

export function hasPermission(permissionNames: string[] | undefined, code: string): boolean {
  if (!permissionNames?.length) return false;
  if (permissionNames.includes("system.admin")) return true;
  return permissionNames.includes(code);
}

/** Presets alinhados a `app/core/permission_codes.ROLE_PRESET` (para aplicar ao mudar perfil na UI). */
export const ROLE_PERMISSION_PRESET: Record<"ADMIN" | "GESTOR" | "CONSULTA", string[]> = {
  ADMIN: [...ALL_PERMISSION_CODES],
  GESTOR: ALL_PERMISSION_CODES.filter(
    (c) => c !== "users.manage" && c !== "system.admin" && c !== "system.all_projects",
  ),
  CONSULTA: [
    "dashboard.view",
    "projects.view",
    "employees.view",
    "vehicles.view",
    "billing.view",
    "invoices.view",
    "debts.view",
    "costs.view",
    "reports.view",
    "alerts.view",
    "company_finance.view",
  ],
};
