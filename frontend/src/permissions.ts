/** Permissões concedidas apenas por checkbox explícito (não herdam de admin/superuser). */
const EXPLICIT_GRANT_ONLY = new Set(["invoices.reactivate", "audit.export"]);

/** Espelha `app/core/permission_codes.ALL_PERMISSION_CODES` (ordem estável para UI). */
export const ALL_PERMISSION_CODES: string[] = [
  "system.admin",
  "system.all_projects",
  "workspace.projects.access",
  "workspace.finance.access",
  "workspace.assets.access",
  "workspace.indicators.access",
  "dashboard.view",
  "dashboard.director",
  "indicators.view",
  "indicators.director",
  "payables.view",
  "receivables.view",
  "payable_snapshot.reconcile",
  "projects.view",
  "projects.view_list",
  "projects.view_detail",
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
  "invoices.reactivate",
  "debts.view",
  "debts.edit",
  "costs.view",
  "costs.edit",
  "settings.view",
  "settings.edit",
  "users.manage",
  "reports.view",
  "reports.export",
  "audit.export",
  "alerts.view",
  "company_finance.view",
  "company_finance.edit",
  "assets.view",
  "assets.edit",
];

export const PERMISSION_LABELS: Record<string, string> = {
  "system.admin": "Administração total",
  "system.all_projects": "Ver todos os projetos",
  "workspace.projects.access": "Workspace Projetos",
  "workspace.finance.access": "Workspace Financeiro",
  "workspace.assets.access": "Workspace Gestão de Ativos",
  "workspace.indicators.access": "Workspace Indicadores",
  "payable_snapshot.reconcile": "Contas a pagar — reconciliar snapshot",
  "indicators.view": "Indicadores (visualizar)",
  "indicators.director": "Indicadores diretoria (ranking global)",
  "dashboard.view": "Dashboard (visualizar)",
  "dashboard.director": "Dashboard diretoria",
  "payables.view": "Contas a pagar (visualizar)",
  "receivables.view": "Contas a receber (visualizar)",
  "projects.view": "Projetos (visualizar)",
  "projects.view_list": "Projetos (listar)",
  "projects.view_detail": "Projetos (detalhe)",
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
  "invoices.reactivate": "Reativar Notas Fiscais Canceladas",
  "debts.view": "Endividamento (visualizar)",
  "debts.edit": "Endividamento (editar)",
  "costs.view": "Custos (visualizar)",
  "costs.edit": "Custos (editar)",
  "settings.view": "Configurações (visualizar)",
  "settings.edit": "Configurações (editar)",
  "users.manage": "Gerenciar usuários",
  "reports.view": "Relatórios (visualizar)",
  "reports.export": "Relatórios (exportar)",
  "audit.export": "Exportar log de auditoria do sistema",
  "alerts.view": "Alertas",
  "company_finance.view": "Finanças empresa (visualizar)",
  "company_finance.edit": "Finanças empresa (editar)",
  "assets.view": "Gestão de ativos (visualizar)",
  "assets.edit": "Gestão de ativos (editar)",
};

export function hasPermission(permissionNames: string[] | undefined, code: string): boolean {
  if (!permissionNames?.length) return false;
  if (EXPLICIT_GRANT_ONLY.has(code)) {
    return permissionNames.includes(code);
  }
  if (permissionNames.includes("system.admin")) return true;
  if (permissionNames.includes(code)) return true;
  if (
    (code === "projects.view_list" || code === "projects.view_detail") &&
    permissionNames.includes("projects.view")
  ) {
    return true;
  }
  if (code === "workspace.projects.access") {
    return permissionNames.some((p) =>
      [
        "dashboard.view",
        "dashboard.director",
        "projects.view",
        "projects.view_list",
        "projects.view_detail",
        "projects.create",
        "projects.edit",
        "projects.delete",
        "employees.view",
        "employees.edit",
        "vehicles.view",
        "vehicles.edit",
        "billing.view",
        "costs.view",
        "costs.edit",
        "reports.view",
        "reports.export",
        "alerts.view",
        "settings.view",
        "settings.edit",
        "users.manage",
      ].includes(p),
    );
  }
  if (code === "workspace.finance.access") {
    return permissionNames.some((p) =>
      [
        "payables.view",
        "receivables.view",
        "invoices.view",
        "invoices.edit",
        "debts.view",
        "debts.edit",
        "company_finance.view",
        "company_finance.edit",
        "reports.view",
        "reports.export",
        "settings.view",
        "settings.edit",
      ].includes(p),
    );
  }
  if (code === "workspace.assets.access") {
    return permissionNames.some((p) =>
      ["assets.view", "assets.edit", "settings.view", "settings.edit"].includes(p),
    );
  }
  if (code === "workspace.indicators.access") {
    return permissionNames.some((p) => ["indicators.view", "indicators.director"].includes(p));
  }
  return false;
}

/** Presets alinhados a `app/core/permission_codes.ROLE_PRESET` (para aplicar ao mudar perfil na UI). */
export const ROLE_PERMISSION_PRESET: Record<"ADMIN" | "GESTOR" | "CONSULTA", string[]> = {
  ADMIN: ALL_PERMISSION_CODES.filter((c) => !EXPLICIT_GRANT_ONLY.has(c)),
  GESTOR: ALL_PERMISSION_CODES.filter(
    (c) => c !== "users.manage" && c !== "system.admin" && c !== "system.all_projects",
  ),
  CONSULTA: [
    "workspace.projects.access",
    "workspace.finance.access",
    "workspace.assets.access",
    "dashboard.view",
    "payables.view",
    "receivables.view",
    "projects.view",
    "projects.view_list",
    "projects.view_detail",
    "employees.view",
    "vehicles.view",
    "billing.view",
    "invoices.view",
    "debts.view",
    "costs.view",
    "reports.view",
    "alerts.view",
    "company_finance.view",
    "assets.view",
  ],
};
