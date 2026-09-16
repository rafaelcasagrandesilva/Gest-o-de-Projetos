import { hasPermission } from "@/permissions";
import type { WorkspaceName } from "@/context/WorkspaceContext";

/**
 * Fonte ÚNICA dos menus de cada Workspace (ordem, rótulo, rota e permissão exigida).
 *
 * É consumida tanto pelas Sidebars (itens visíveis) quanto pelo resolvedor de rota inicial
 * (`resolveWorkspaceLanding`). Não deve existir nenhuma outra lista de menus/permissões espalhada
 * pelo frontend — assim a navegação inicial e a barra lateral nunca divergem.
 *
 * IMPORTANTE: isto é APENAS navegação. A autorização real continua no backend (endpoints) e em
 * cada tela; este arquivo não concede nem revoga permissão alguma.
 */
export type WorkspaceMenuItem = {
  to: string;
  label: string;
  /** Permissão exigida para ver o item. Array = QUALQUER uma das permissões (any-of). */
  perm: string | string[];
  /** Abreviação fixa com a sidebar recolhida; sem ela, iniciais do rótulo (até 3 letras). */
  short?: string;
  /** NavLink `end` (match exato da rota). */
  end?: boolean;
};

// "Configurações" fica só no workspace Projetos: settings.read OU audit.export (quem só exporta auditoria chega à aba).
const SETTINGS_ITEM: WorkspaceMenuItem = {
  to: "/settings",
  label: "Configurações",
  perm: ["settings.read", "audit.export"],
  end: false,
};

export const WORKSPACE_MENUS: Record<WorkspaceName, WorkspaceMenuItem[]> = {
  projects: [
    { to: "/projects/dashboard", label: "Dashboard operacional", perm: "dashboard.read", end: true },
    { to: "/projects/list", label: "Projetos", perm: "projects.list" },
    { to: "/projects/agenda", label: "Agenda", perm: "project_agenda.list" },
    { to: "/projects/employees", label: "Colaboradores", perm: "employees.read" },
    { to: "/projects/vehicles", label: "Veículos", perm: "vehicles.read" },
    { to: "/projects/revenue", label: "Faturamento", perm: "billing.read" },
    { to: "/projects/reports", label: "Relatórios", perm: "reports.read" },
    { to: "/projects/users", label: "Usuários", perm: "users.manage" },
    SETTINGS_ITEM,
  ],
  finance: [
    { to: "/finance/dashboard", label: "Dashboard", short: "DO", perm: "financial_dashboard.read", end: true },
    { to: "/finance/payables", label: "Contas a pagar", perm: "payables.read" },
    { to: "/finance/receivables", label: "Contas a receber", perm: "receivables.read" },
    { to: "/finance/invoices", label: "Notas fiscais (NFs)", short: "NF's", perm: "invoices.read" },
    { to: "/finance/advance-batches", label: "Antecipações", short: "ANT", perm: "invoices.read" },
    { to: "/finance/debt", label: "Endividamento", short: "END", perm: "debts.read" },
    { to: "/finance/fixed-costs", label: "Custos Indiretos", perm: "company_finance.read" },
    { to: "/finance/reports", label: "Relatórios", perm: "reports.read" },
  ],
  assets: [
    { to: "/assets/dashboard", label: "Dashboard", short: "DO", perm: "assets.list" },
    { to: "/assets", label: "Patrimônio", short: "PTM", perm: "assets.list", end: true },
    { to: "/epis", label: "EPIs", short: "EPIs", perm: "assets.list", end: true },
  ],
  indicators: [
    { to: "/indicators/roi", label: "ROI Operacional", perm: "indicators.read" },
    { to: "/indicators/evolucao-financeira", label: "Evolução Financeira", perm: "indicators.read" },
    { to: "/indicators/resultado-empresa", label: "Resultado da Empresa", short: "RE", perm: "company_result.read" },
  ],
  legal: [
    // O Painel do passivo abre o menu — e, por consequência, é a tela de entrada do workspace
    // (a navegação inicial usa o primeiro item permitido).
    { to: "/legal/dashboard", label: "Painel do passivo", short: "DO", perm: "legal_dashboard.read" },
    { to: "/legal/central", label: "Central de Trabalho", short: "CT", perm: "legal_cases.list", end: true },
    { to: "/legal/agenda", label: "Agenda", perm: "legal_cases.list" },
    { to: "/legal/cases", label: "Processos", perm: "legal_cases.list" },
    { to: "/legal/persons", label: "Desligados", perm: "legal_persons.list" },
    // Manutenção dos dados — exige poder ALTERAR alguma das quatro entidades, OU importar
    // (a aba Importações vive aqui dentro: sem `legal_imports.*` na lista, quem recebe só a
    // permissão de importar não teria como CHEGAR à tela). Só leitura não vê o menu.
    {
      to: "/legal/admin",
      label: "Administração",
      perm: [
        "legal_cases.create", "legal_cases.update", "legal_cases.delete",
        "legal_persons.create", "legal_persons.update", "legal_persons.delete",
        "legal_companies.create", "legal_companies.update", "legal_companies.delete",
        "legal_projects.create", "legal_projects.update", "legal_projects.delete",
        "legal_imports.list", "legal_imports.create",
      ],
    },
    { to: "/legal/reports", label: "Relatórios", perm: "legal_reports.read" },
  ],
};

/** True se o usuário tem a permissão do item (any-of quando `perm` é lista). */
export function isMenuItemAllowed(item: WorkspaceMenuItem, permissions: string[] | undefined): boolean {
  const codes = Array.isArray(item.perm) ? item.perm : [item.perm];
  return codes.some((code) => hasPermission(permissions, code));
}

/** Itens visíveis do Workspace, na ordem canônica — usado pelas Sidebars. */
export function visibleWorkspaceMenu(
  workspace: WorkspaceName,
  permissions: string[] | undefined,
): WorkspaceMenuItem[] {
  return (WORKSPACE_MENUS[workspace] ?? []).filter((item) => isMenuItemAllowed(item, permissions));
}

/**
 * Rota inicial do Workspace = PRIMEIRA tela permitida (na ordem canônica dos menus).
 * Retorna `null` quando o usuário não tem acesso a nenhuma tela do Workspace
 * (aí a UI deve mostrar "Sem permissão").
 */
export function resolveWorkspaceLanding(
  workspace: WorkspaceName,
  permissions: string[] | undefined,
): string | null {
  const first = (WORKSPACE_MENUS[workspace] ?? []).find((item) => isMenuItemAllowed(item, permissions));
  return first ? first.to : null;
}
