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
  "payables.edit",
  "receivables.view",
  "receivables.edit",
  "payable_snapshot.reconcile",
  "projects.view",
  "projects.view_list",
  "projects.view_detail",
  "projects.create",
  "projects.edit",
  "projects.delete",
  "projects.documents.view",
  "projects.documents.upload",
  "projects.documents.delete",
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
  // --- Modelo de verbos (Etapa 0) — códigos novos, inativos até a etapa do módulo ---
  "employees.reference",
  "employees.list",
  "employees.read",
  "employees.create",
  "employees.update",
  "employees.delete",
  "employees.sensitive",
  "employees.export",
  "assets.reference",
  "assets.list",
  "assets.read",
  "assets.create",
  "assets.update",
  "assets.delete",
  "assets.sensitive",
  "vehicles.reference",
  "vehicles.list",
  "vehicles.read",
  "vehicles.create",
  "vehicles.update",
  "vehicles.delete",
  "vehicles.sensitive",
  "vehicles.export",
  "projects.reference",
  "projects.list",
  "projects.read",
  "projects.update",
  "projects.sensitive",
  "cost_center.reference",
  // Financeiro (verbos) — espelham os códigos do backend p/ a grade de administração.
  "payables.list", "payables.read", "payables.create", "payables.update", "payables.delete", "payables.sensitive",
  "receivables.list", "receivables.read", "receivables.create", "receivables.update", "receivables.delete", "receivables.sensitive",
  "invoices.list", "invoices.read", "invoices.create", "invoices.update", "invoices.delete", "invoices.sensitive",
  "debts.list", "debts.read", "debts.create", "debts.update", "debts.delete", "debts.sensitive",
  "costs.list", "costs.read", "costs.create", "costs.update", "costs.delete", "costs.sensitive",
  "company_finance.list", "company_finance.read", "company_finance.create", "company_finance.update", "company_finance.delete", "company_finance.sensitive",
  "billing.list", "billing.read", "billing.create", "billing.update", "billing.delete", "billing.sensitive",
  // Leitura/gestão (verbos aplicáveis).
  "indicators.read", "indicators.sensitive",
  "dashboard.read", "dashboard.sensitive",
  "financial_dashboard.read", "financial_dashboard.sensitive",
  "reports.read",
  "settings.read", "settings.update",
  "alerts.read",
];

/** Códigos NOVOS do modelo de verbos (espelha `permission_codes.NEW_PERMISSION_CODES`). */
export const NEW_PERMISSION_CODES: string[] = [
  "employees.reference",
  "employees.list",
  "employees.read",
  "employees.create",
  "employees.update",
  "employees.delete",
  "employees.sensitive",
  "employees.export",
  "assets.reference",
  "assets.list",
  "assets.read",
  "assets.create",
  "assets.update",
  "assets.delete",
  "assets.sensitive",
  "vehicles.reference",
  "vehicles.list",
  "vehicles.read",
  "vehicles.create",
  "vehicles.update",
  "vehicles.delete",
  "vehicles.sensitive",
  "vehicles.export",
  "projects.reference",
  "projects.list",
  "projects.read",
  "projects.update",
  "projects.sensitive",
  "cost_center.reference",
  // Financeiro (verbos) — espelham os códigos do backend p/ a grade de administração.
  "payables.list", "payables.read", "payables.create", "payables.update", "payables.delete", "payables.sensitive",
  "receivables.list", "receivables.read", "receivables.create", "receivables.update", "receivables.delete", "receivables.sensitive",
  "invoices.list", "invoices.read", "invoices.create", "invoices.update", "invoices.delete", "invoices.sensitive",
  "debts.list", "debts.read", "debts.create", "debts.update", "debts.delete", "debts.sensitive",
  "costs.list", "costs.read", "costs.create", "costs.update", "costs.delete", "costs.sensitive",
  "company_finance.list", "company_finance.read", "company_finance.create", "company_finance.update", "company_finance.delete", "company_finance.sensitive",
  "billing.list", "billing.read", "billing.create", "billing.update", "billing.delete", "billing.sensitive",
  // Leitura/gestão (verbos aplicáveis).
  "indicators.read", "indicators.sensitive",
  "dashboard.read", "dashboard.sensitive",
  "financial_dashboard.read", "financial_dashboard.sensitive",
  "reports.read",
  "settings.read", "settings.update",
  "alerts.read",
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
  "financial_dashboard.read": "Dashboard financeiro · Visualizar",
  "financial_dashboard.sensitive": "Dashboard financeiro · Dados sensíveis",
  "payables.view": "Contas a pagar (visualizar)",
  "payables.edit": "Contas a pagar (editar)",
  "receivables.view": "Contas a receber (visualizar)",
  "receivables.edit": "Contas a receber (editar)",
  "projects.view": "Projetos (visualizar)",
  "projects.view_list": "Projetos (listar)",
  "projects.view_detail": "Projetos (detalhe)",
  "projects.create": "Projetos (criar)",
  "projects.edit": "Projetos (editar)",
  "projects.delete": "Projetos (excluir)",
  "projects.documents.view": "Projetos · Documentos (visualizar)",
  "projects.documents.upload": "Projetos · Documentos (enviar)",
  "projects.documents.delete": "Projetos · Documentos (excluir)",
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
  // --- Modelo de verbos (Etapa 0) ---
  "employees.reference": "Colaboradores · Referenciar",
  "employees.list": "Colaboradores · Listar",
  "employees.read": "Colaboradores · Visualizar",
  "employees.create": "Colaboradores · Criar",
  "employees.update": "Colaboradores · Editar",
  "employees.delete": "Colaboradores · Excluir",
  "employees.sensitive": "Colaboradores · Dados sensíveis",
  "employees.export": "Colaboradores · Exportar",
  "assets.reference": "Ativos · Referenciar",
  "assets.list": "Ativos · Listar",
  "assets.read": "Ativos · Visualizar",
  "assets.create": "Ativos · Criar",
  "assets.update": "Ativos · Editar",
  "assets.delete": "Ativos · Excluir",
  "assets.sensitive": "Ativos · Dados sensíveis",
  "vehicles.reference": "Veículos · Referenciar",
  "vehicles.list": "Veículos · Listar",
  "vehicles.read": "Veículos · Visualizar",
  "vehicles.create": "Veículos · Criar",
  "vehicles.update": "Veículos · Editar",
  "vehicles.delete": "Veículos · Excluir",
  "vehicles.sensitive": "Veículos · Dados sensíveis",
  "vehicles.export": "Veículos · Exportar",
  "projects.reference": "Projetos · Referenciar",
  "projects.list": "Projetos · Listar",
  "projects.read": "Projetos · Visualizar",
  "projects.update": "Projetos · Editar",
  "projects.sensitive": "Projetos · Dados sensíveis",
  "cost_center.reference": "Centro de Custo · Referenciar",
};

/**
 * Grafo de implicação (espelha `app/core/permission_codes.PERMISSION_IMPLIES`).
 * "A → [B, C]" = quem tem A tem B e C. O fecho é calculado por `expandPermissions`.
 */
const PERMISSION_IMPLIES: Record<string, string[]> = {
  // system.admin: só administração do próprio sistema (Fase 1) — nunca módulos de negócio.
  "system.admin": ["users.manage", "settings.view", "settings.edit"],
  "projects.view": ["projects.view_list", "projects.view_detail", "projects.read", "projects.sensitive"],
  "projects.edit": ["projects.update", "projects.sensitive"],
  "projects.update": ["projects.read", "cost_center.reference"],
  "projects.delete": ["projects.read"],
  "projects.create": ["projects.reference", "cost_center.reference"],
  "projects.read": ["projects.list"],
  "projects.list": ["projects.reference"],
  // Financeiro (CRUD) — view⇒read/sensitive, edit⇒create/update/delete/sensitive.
  "payables.update": ["payables.read"], "payables.delete": ["payables.read"], "payables.create": ["payables.read"], "payables.read": ["payables.list"],
  "payables.view": ["payables.read", "payables.sensitive"], "payables.edit": ["payables.create", "payables.update", "payables.delete", "payables.sensitive"],
  "receivables.update": ["receivables.read"], "receivables.delete": ["receivables.read"], "receivables.create": ["receivables.read"], "receivables.read": ["receivables.list"],
  "receivables.view": ["receivables.read", "receivables.sensitive"], "receivables.edit": ["receivables.create", "receivables.update", "receivables.delete", "receivables.sensitive"],
  "invoices.update": ["invoices.read"], "invoices.delete": ["invoices.read"], "invoices.create": ["invoices.read"], "invoices.read": ["invoices.list"],
  "invoices.view": ["invoices.read", "invoices.sensitive"], "invoices.edit": ["invoices.create", "invoices.update", "invoices.delete", "invoices.sensitive"],
  "debts.update": ["debts.read"], "debts.delete": ["debts.read"], "debts.create": ["debts.read"], "debts.read": ["debts.list"],
  "debts.view": ["debts.read", "debts.sensitive"], "debts.edit": ["debts.create", "debts.update", "debts.delete", "debts.sensitive"],
  "costs.update": ["costs.read"], "costs.delete": ["costs.read"], "costs.create": ["costs.read"], "costs.read": ["costs.list"],
  "costs.view": ["costs.read", "costs.sensitive"], "costs.edit": ["costs.create", "costs.update", "costs.delete", "costs.sensitive"],
  "company_finance.update": ["company_finance.read"], "company_finance.delete": ["company_finance.read"], "company_finance.create": ["company_finance.read"], "company_finance.read": ["company_finance.list"],
  "company_finance.view": ["company_finance.read", "company_finance.sensitive", "cost_center.reference"], "company_finance.edit": ["company_finance.create", "company_finance.update", "company_finance.delete", "company_finance.sensitive"],
  "billing.update": ["billing.read"], "billing.delete": ["billing.read"], "billing.create": ["billing.read"], "billing.read": ["billing.list"],
  "billing.view": ["billing.read", "billing.sensitive"],
  // Leitura — view⇒read (+ sensitive onde há valores).
  "indicators.view": ["indicators.read", "indicators.sensitive"],
  "dashboard.view": ["dashboard.read", "dashboard.sensitive"],
  "alerts.view": ["alerts.read"],
  "reports.view": ["reports.read"],
  "settings.view": ["settings.read"], "settings.edit": ["settings.update", "settings.read"],
  "employees.update": ["employees.read", "cost_center.reference"],
  "employees.delete": ["employees.read"],
  "employees.create": ["employees.reference", "cost_center.reference"],
  "employees.read": ["employees.list"],
  "employees.list": ["employees.reference"],
  "assets.update": ["assets.read", "cost_center.reference"],
  "assets.delete": ["assets.read"],
  "assets.create": ["assets.reference", "cost_center.reference"],
  "assets.read": ["assets.list"],
  "assets.list": ["assets.reference"],
  "vehicles.update": ["vehicles.read", "cost_center.reference"],
  "vehicles.delete": ["vehicles.read"],
  "vehicles.create": ["vehicles.reference", "cost_center.reference"],
  "vehicles.read": ["vehicles.list"],
  "vehicles.list": ["vehicles.reference"],
  "employees.view": ["employees.read", "employees.sensitive", "employees.export", "cost_center.reference"],
  "employees.edit": ["employees.create", "employees.update", "employees.delete", "employees.sensitive", "employees.export"],
  "assets.view": ["assets.read", "assets.sensitive", "cost_center.reference"],
  "assets.edit": ["assets.create", "assets.update", "assets.delete", "assets.sensitive"],
  "vehicles.view": ["vehicles.read", "vehicles.sensitive", "vehicles.export", "cost_center.reference"],
  "vehicles.edit": ["vehicles.create", "vehicles.update", "vehicles.delete", "vehicles.sensitive", "vehicles.export"],
  "projects.view_list": ["cost_center.reference"],
};

/** Fecho transitivo de `held` sob `PERMISSION_IMPLIES` (inclui os próprios códigos). */
export function expandPermissions(held: string[]): Set<string> {
  const seen = new Set(held);
  const stack = [...held];
  while (stack.length) {
    const cur = stack.pop() as string;
    for (const nxt of PERMISSION_IMPLIES[cur] ?? []) {
      if (!seen.has(nxt)) {
        seen.add(nxt);
        stack.push(nxt);
      }
    }
  }
  return seen;
}

/** Recurso (chave) → rótulo pt-BR (linha da grade de administração). */
export const RESOURCE_LABELS: Record<string, string> = {
  employees: "Colaboradores",
  vehicles: "Veículos",
  assets: "Ativos",
  projects: "Projetos",
  cost_center: "Centro de Custo",
  payables: "Contas a pagar",
  receivables: "Contas a receber",
  invoices: "Notas fiscais",
  debts: "Endividamento",
  // "Custos" gate a API de custos de projeto/rateio corporativo (/costs/*). "Finanças da
  // empresa" controla a tela "Custos Fixos - Matriz" — rótulos alinhados às funcionalidades.
  costs: "Custos de projeto (rateio)",
  company_finance: "Finanças da empresa (Custos Fixos - Matriz)",
  billing: "Faturamento",
  dashboard: "Dashboard",
  financial_dashboard: "Dashboard financeiro",
  indicators: "Indicadores",
  reports: "Relatórios",
  alerts: "Alertas",
  audit: "Auditoria",
  users: "Usuários",
  settings: "Configurações",
  workspace_projects: "Workspace Projetos",
  workspace_finance: "Workspace Financeiro",
  workspace_assets: "Workspace Gestão de Ativos",
  workspace_indicators: "Workspace Indicadores",
  system_admin: "Administração do sistema",
  system_all_projects: "Escopo global de projetos",
  project_documents: "Documentos do projeto",
};

/**
 * Agrupamento lógico dos recursos na grade. MODELO ÚNICO: toda permissão administrável aparece na
 * grade (não existe mais a seção "Outras permissões"). Recursos com célula fora de qualquer grupo
 * caem em "Outros recursos" (salvaguarda — não deve ocorrer).
 */
export const RESOURCE_GROUPS: { label: string; resources: string[] }[] = [
  { label: "Cadastros", resources: ["employees", "vehicles", "assets", "projects", "cost_center"] },
  { label: "Financeiro", resources: ["financial_dashboard", "payables", "receivables", "invoices", "debts", "costs", "company_finance", "billing"] },
  { label: "Gestão", resources: ["dashboard", "indicators", "reports", "alerts", "audit"] },
  {
    label: "Sistema",
    resources: [
      "users",
      "settings",
      "workspace_projects",
      "workspace_finance",
      "workspace_assets",
      "workspace_indicators",
      "system_admin",
      "system_all_projects",
      "project_documents",
    ],
  },
];

/**
 * Ações (COLUNAS) — modelo visual ÚNICO. Além do CRUD, colunas transversais dão lugar na grade a
 * permissões que não são CRUD de um recurso, sem uma lista à parte:
 *   - export    (Exportar):    reports.export, audit.export
 *   - execute   (Executar):    operações privilegiadas pontuais (invoices.reactivate, payable_snapshot.reconcile)
 *   - director  (Diretoria):   visão consolidada/global (dashboard.director, indicators.director)
 *   - access    (Acessar):     liberar área/escopo (workspace.*.access, system.all_projects)
 *   - manage    (Administrar): gestão/administração plena (users.manage, system.admin)
 * "Dados sensíveis" (sensitive) é sempre a última coluna.
 */
export const COLUMN_ORDER = [
  "reference",
  "list",
  "read",
  "create",
  "update",
  "delete",
  "export",
  "execute",
  "director",
  "access",
  "manage",
  "sensitive",
] as const;

export type PermissionColumn = (typeof COLUMN_ORDER)[number];

export const COLUMN_LABELS: Record<PermissionColumn, string> = {
  reference: "Referenciar",
  list: "Listar",
  read: "Visualizar",
  create: "Criar",
  update: "Editar",
  delete: "Excluir",
  export: "Exportar",
  execute: "Executar",
  director: "Diretoria",
  access: "Acessar",
  manage: "Administrar",
  sensitive: "Dados sensíveis",
};

// Compatibilidade: aliases antigos (a grade passou de "verbo" para "coluna/ação").
export const VERB_ORDER = COLUMN_ORDER;
export const VERB_LABELS: Record<string, string> = COLUMN_LABELS;

/**
 * Colunas cujo código segue exatamente `${resource}.${column}` (derivação automática). As colunas
 * `access` e `execute` nunca aparecem como sufixo literal — só via `CODE_PLACEMENT`.
 */
const DERIVED_COLUMNS = new Set<string>([
  "reference",
  "list",
  "read",
  "create",
  "update",
  "delete",
  "export",
  "director",
  "manage",
  "sensitive",
]);

/**
 * Placement EXPLÍCITO para códigos que NÃO seguem `${resource}.${column}`. É só reorganização de
 * INTERFACE: o código enviado ao backend continua idêntico (nenhuma permissão nova, nenhuma semântica
 * alterada). Todo o resto deriva de `${resource}.${column}`.
 */
const CODE_PLACEMENT: Record<string, { resource: string; column: PermissionColumn }> = {
  "system.admin": { resource: "system_admin", column: "manage" },
  "system.all_projects": { resource: "system_all_projects", column: "access" },
  "workspace.projects.access": { resource: "workspace_projects", column: "access" },
  "workspace.finance.access": { resource: "workspace_finance", column: "access" },
  "workspace.assets.access": { resource: "workspace_assets", column: "access" },
  "workspace.indicators.access": { resource: "workspace_indicators", column: "access" },
  "invoices.reactivate": { resource: "invoices", column: "execute" },
  "payable_snapshot.reconcile": { resource: "payables", column: "execute" },
  "projects.documents.view": { resource: "project_documents", column: "read" },
  "projects.documents.upload": { resource: "project_documents", column: "create" },
  "projects.documents.delete": { resource: "project_documents", column: "delete" },
};

/** Entrada do catálogo da grade: recurso + coluna(ação) → código. */
export type PermissionGridCell = { resource: string; column: PermissionColumn; code: string };

/** Onde um código aparece na grade — ou `null` (alias legado oculto, preservado no set ao salvar). */
function codePlacement(code: string): { resource: string; column: PermissionColumn } | null {
  const explicit = CODE_PLACEMENT[code];
  if (explicit) return explicit;
  const i = code.indexOf(".");
  if (i < 0) return null;
  const resource = code.slice(0, i);
  const column = code.slice(i + 1);
  if (DERIVED_COLUMNS.has(column) && resource in RESOURCE_LABELS) {
    return { resource, column: column as PermissionColumn };
  }
  return null;
}

/** recurso → (coluna → código), construído a partir de `ALL_PERMISSION_CODES`. Fonte única da grade. */
const RESOURCE_CELLS: Map<string, Map<PermissionColumn, string>> = (() => {
  const m = new Map<string, Map<PermissionColumn, string>>();
  for (const code of ALL_PERMISSION_CODES) {
    const pl = codePlacement(code);
    if (!pl) continue;
    if (!m.has(pl.resource)) m.set(pl.resource, new Map());
    m.get(pl.resource)!.set(pl.column, code);
  }
  return m;
})();

const _cellsFor = (resource: string): PermissionGridCell[] => {
  const byCol = RESOURCE_CELLS.get(resource);
  if (!byCol) return [];
  return COLUMN_ORDER.filter((c) => byCol.has(c)).map((c) => ({
    resource,
    column: c,
    code: byCol.get(c) as string,
  }));
};

/** Grade agrupada. Todo recurso com ao menos uma célula aparece no seu grupo. */
export function permissionGridGroups(): {
  group: string;
  resources: { resource: string; cells: PermissionGridCell[] }[];
}[] {
  const grouped = new Set<string>();
  const out = RESOURCE_GROUPS.map((g) => {
    const resources = g.resources
      .filter((r) => RESOURCE_CELLS.has(r))
      .map((r) => {
        grouped.add(r);
        return { resource: r, cells: _cellsFor(r) };
      });
    return { group: g.label, resources };
  }).filter((g) => g.resources.length > 0);
  const ungrouped = [...RESOURCE_CELLS.keys()].filter((r) => !grouped.has(r));
  if (ungrouped.length) {
    out.push({ group: "Outros recursos", resources: ungrouped.map((r) => ({ resource: r, cells: _cellsFor(r) })) });
  }
  return out;
}

/** Grade achatada (todos os recursos, sem grupo). */
export function permissionGrid(): { resource: string; cells: PermissionGridCell[] }[] {
  return permissionGridGroups().flatMap((g) => g.resources);
}

/** Todos os códigos representados por uma célula da grade. */
export const GRID_CODES = new Set(permissionGrid().flatMap((g) => g.cells.map((c) => c.code)));

/**
 * Códigos LEGADOS redundantes (aliases `<r>.view/.edit/.view_list/.view_detail`) cujo comportamento
 * já é representado pelos verbos na grade. Ficam OCULTOS, mas PRESERVADOS no conjunto do formulário
 * (nunca são removidos ao salvar). Nenhuma permissão é alterada — a UI apenas deixa de duplicá-los.
 */
export const LEGACY_HIDDEN_CODES = new Set(ALL_PERMISSION_CODES.filter((c) => !GRID_CODES.has(c)));

/**
 * Salvaguarda: todo código do catálogo deve estar na grade OU ser um alias legado conhecido
 * (`.view/.edit/.view_list/.view_detail`). Se algo escapar, aparece aqui (deve ser sempre vazio) —
 * garantia de que 100% das permissões estão representadas e nada "desaparece".
 */
export const UNMAPPED_CODES = [...LEGACY_HIDDEN_CODES].filter(
  (c) => !/\.(view|edit|view_list|view_detail)$/.test(c),
);
if (import.meta.env?.DEV && UNMAPPED_CODES.length) {
  // eslint-disable-next-line no-console
  console.warn("[permissions] códigos sem célula na grade e sem alias legado:", UNMAPPED_CODES);
}

export function hasPermission(permissionNames: string[] | undefined, code: string): boolean {
  if (!permissionNames?.length) return false;
  if (EXPLICIT_GRANT_ONLY.has(code)) {
    return permissionNames.includes(code);
  }
  // Fase 1: sem atalho "system.admin libera tudo". Acesso vem só das permissões (via grafo).
  // system.admin só implica as funcionalidades administrativas do sistema (edge no grafo acima).
  if (expandPermissions(permissionNames).has(code)) return true;
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
        "financial_dashboard.read",
        "payables.view",
        "payables.edit",
        "receivables.view",
        "receivables.edit",
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
    "financial_dashboard.read",
    "financial_dashboard.sensitive",
    // Modelo de verbos (equivalente a *.view legado): leitura + sensitive, sem CRUD.
    "employees.reference",
    "employees.list",
    "employees.read",
    "employees.sensitive",
    "assets.reference",
    "assets.list",
    "assets.read",
    "vehicles.reference",
    "vehicles.list",
    "vehicles.read",
    "vehicles.sensitive",
    "cost_center.reference",
  ],
};
