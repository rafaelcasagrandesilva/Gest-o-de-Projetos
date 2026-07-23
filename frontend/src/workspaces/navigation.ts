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
  /** NavLink `end` (match exato da rota). */
  end?: boolean;
};

// Item compartilhado "Configurações" (mesma regra usada hoje nas Sidebars: settings.view OU audit.export).
const SETTINGS_ITEM: WorkspaceMenuItem = {
  to: "/settings",
  label: "Configurações",
  perm: ["settings.view", "audit.export"],
  end: false,
};

export const WORKSPACE_MENUS: Record<WorkspaceName, WorkspaceMenuItem[]> = {
  projects: [
    { to: "/projects/dashboard", label: "Dashboard operacional", perm: "dashboard.read", end: true },
    { to: "/projects/reports", label: "Relatórios", perm: "reports.read" },
    { to: "/projects/list", label: "Projetos", perm: "projects.list" },
    { to: "/projects/users", label: "Usuários", perm: "users.manage" },
    { to: "/projects/employees", label: "Colaboradores", perm: "employees.read" },
    { to: "/projects/vehicles", label: "Veículos", perm: "vehicles.read" },
    { to: "/projects/revenue", label: "Faturamento", perm: "billing.read" },
    SETTINGS_ITEM,
  ],
  finance: [
    { to: "/finance/dashboard", label: "Dashboard", perm: "financial_dashboard.read", end: true },
    { to: "/finance/payables", label: "Contas a pagar", perm: "payables.read" },
    { to: "/finance/receivables", label: "Contas a receber", perm: "receivables.read" },
    { to: "/finance/invoices", label: "Notas fiscais (NFs)", perm: "invoices.read" },
    { to: "/finance/advance-batches", label: "Antecipações", perm: "invoices.read" },
    { to: "/finance/advance-institutions", label: "Instituições de Antecipação", perm: "invoices.read" },
    { to: "/finance/debt", label: "Endividamento", perm: "debts.read" },
    { to: "/finance/fixed-costs", label: "Custos Fixos - Matriz", perm: "company_finance.read" },
    { to: "/finance/reports", label: "Relatórios", perm: "reports.read" },
    SETTINGS_ITEM,
  ],
  assets: [
    { to: "/assets/dashboard", label: "Dashboard", perm: "assets.list" },
    { to: "/assets", label: "Patrimônio", perm: "assets.list", end: true },
    { to: "/epis", label: "EPIs", perm: "assets.list", end: true },
    SETTINGS_ITEM,
  ],
  indicators: [
    { to: "/indicators/roi", label: "ROI Operacional", perm: "indicators.read" },
    { to: "/indicators/evolucao-financeira", label: "Evolução Financeira", perm: "indicators.read" },
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
