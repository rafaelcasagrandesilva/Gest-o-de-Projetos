"""Códigos de permissão (nome estável em banco e API)."""

from __future__ import annotations

# Metadados
SYSTEM_ADMIN = "system.admin"
SYSTEM_ALL_PROJECTS = "system.all_projects"

# Módulos
WORKSPACE_PROJECTS_ACCESS = "workspace.projects.access"
WORKSPACE_FINANCE_ACCESS = "workspace.finance.access"
WORKSPACE_ASSETS_ACCESS = "workspace.assets.access"
WORKSPACE_INDICATORS_ACCESS = "workspace.indicators.access"

DASHBOARD_VIEW = "dashboard.view"
DASHBOARD_DIRECTOR = "dashboard.director"

# Indicadores (KPIs): view = ver indicadores dos projetos visíveis;
# director = ranking global / consolidado de todos os projetos.
INDICATORS_VIEW = "indicators.view"
INDICATORS_DIRECTOR = "indicators.director"

PROJECTS_VIEW = "projects.view"
# Granularidade futura: listagem vs detalhe (hoje equivalentes a projects.view no backend).
PROJECTS_VIEW_LIST = "projects.view_list"
PROJECTS_VIEW_DETAIL = "projects.view_detail"
PROJECTS_CREATE = "projects.create"
PROJECTS_EDIT = "projects.edit"
PROJECTS_DELETE = "projects.delete"

EMPLOYEES_VIEW = "employees.view"
EMPLOYEES_EDIT = "employees.edit"

VEHICLES_VIEW = "vehicles.view"
VEHICLES_EDIT = "vehicles.edit"

BILLING_VIEW = "billing.view"

PAYABLES_VIEW = "payables.view"
RECEIVABLES_VIEW = "receivables.view"
# Reconciliar snapshot de Contas a Pagar: marcar lançamentos automáticos cuja
# origem foi removida (resíduos) e permitir limpeza manual. Operação sensível,
# separada de payables.view e do superusuário do "Regenerar Snapshot".
PAYABLE_SNAPSHOT_RECONCILE = "payable_snapshot.reconcile"

INVOICES_VIEW = "invoices.view"
INVOICES_EDIT = "invoices.edit"
# Concedida apenas por marcação explícita em user_permissions (não herda de ADMIN/superuser).
INVOICES_REACTIVATE = "invoices.reactivate"

DEBTS_VIEW = "debts.view"
DEBTS_EDIT = "debts.edit"

COSTS_VIEW = "costs.view"
COSTS_EDIT = "costs.edit"

SETTINGS_VIEW = "settings.view"
SETTINGS_EDIT = "settings.edit"

USERS_MANAGE = "users.manage"

REPORTS_VIEW = "reports.view"
REPORTS_EXPORT = "reports.export"
# Concedida apenas por marcação explícita (exportação do log de auditoria do sistema).
AUDIT_EXPORT = "audit.export"

ALERTS_VIEW = "alerts.view"

COMPANY_FINANCE_VIEW = "company_finance.view"
COMPANY_FINANCE_EDIT = "company_finance.edit"

ASSETS_VIEW = "assets.view"
ASSETS_EDIT = "assets.edit"

ALL_PERMISSION_CODES: tuple[str, ...] = (
    SYSTEM_ADMIN,
    SYSTEM_ALL_PROJECTS,
    WORKSPACE_PROJECTS_ACCESS,
    WORKSPACE_FINANCE_ACCESS,
    WORKSPACE_ASSETS_ACCESS,
    WORKSPACE_INDICATORS_ACCESS,
    DASHBOARD_VIEW,
    DASHBOARD_DIRECTOR,
    INDICATORS_VIEW,
    INDICATORS_DIRECTOR,
    PROJECTS_VIEW,
    PROJECTS_VIEW_LIST,
    PROJECTS_VIEW_DETAIL,
    PROJECTS_CREATE,
    PROJECTS_EDIT,
    PROJECTS_DELETE,
    EMPLOYEES_VIEW,
    EMPLOYEES_EDIT,
    VEHICLES_VIEW,
    VEHICLES_EDIT,
    BILLING_VIEW,
    PAYABLES_VIEW,
    RECEIVABLES_VIEW,
    PAYABLE_SNAPSHOT_RECONCILE,
    INVOICES_VIEW,
    INVOICES_EDIT,
    INVOICES_REACTIVATE,
    DEBTS_VIEW,
    DEBTS_EDIT,
    COSTS_VIEW,
    COSTS_EDIT,
    SETTINGS_VIEW,
    SETTINGS_EDIT,
    USERS_MANAGE,
    REPORTS_VIEW,
    REPORTS_EXPORT,
    AUDIT_EXPORT,
    ALERTS_VIEW,
    COMPANY_FINANCE_VIEW,
    COMPANY_FINANCE_EDIT,
    ASSETS_VIEW,
    ASSETS_EDIT,
)

# Permissões que só valem se estiverem em user_permissions (checkbox na gestão de usuários).
EXPLICIT_GRANT_ONLY_PERMISSIONS = frozenset({INVOICES_REACTIVATE, AUDIT_EXPORT})

# Compatibilidade com perfis legados (seed / ajuste em massa)
PRESET_ADMIN = frozenset(ALL_PERMISSION_CODES) - EXPLICIT_GRANT_ONLY_PERMISSIONS

PRESET_GESTOR = frozenset(
    {
        WORKSPACE_PROJECTS_ACCESS,
        WORKSPACE_FINANCE_ACCESS,
        DASHBOARD_VIEW,
        DASHBOARD_DIRECTOR,
        WORKSPACE_INDICATORS_ACCESS,
        INDICATORS_VIEW,
        INDICATORS_DIRECTOR,
        PROJECTS_VIEW,
        PROJECTS_VIEW_LIST,
        PROJECTS_VIEW_DETAIL,
        PROJECTS_CREATE,
        PROJECTS_EDIT,
        PROJECTS_DELETE,
        EMPLOYEES_VIEW,
        EMPLOYEES_EDIT,
        VEHICLES_VIEW,
        VEHICLES_EDIT,
        BILLING_VIEW,
        PAYABLES_VIEW,
        RECEIVABLES_VIEW,
        PAYABLE_SNAPSHOT_RECONCILE,
        INVOICES_VIEW,
        INVOICES_EDIT,
        DEBTS_VIEW,
        DEBTS_EDIT,
        COSTS_VIEW,
        COSTS_EDIT,
        REPORTS_VIEW,
        REPORTS_EXPORT,
        ALERTS_VIEW,
        COMPANY_FINANCE_VIEW,
        COMPANY_FINANCE_EDIT,
        WORKSPACE_ASSETS_ACCESS,
        ASSETS_VIEW,
        ASSETS_EDIT,
        SETTINGS_VIEW,
        SETTINGS_EDIT,
    }
)

PRESET_CONSULTA = frozenset(
    {
        WORKSPACE_PROJECTS_ACCESS,
        WORKSPACE_FINANCE_ACCESS,
        DASHBOARD_VIEW,
        WORKSPACE_INDICATORS_ACCESS,
        INDICATORS_VIEW,
        PROJECTS_VIEW,
        PROJECTS_VIEW_LIST,
        PROJECTS_VIEW_DETAIL,
        EMPLOYEES_VIEW,
        VEHICLES_VIEW,
        BILLING_VIEW,
        PAYABLES_VIEW,
        RECEIVABLES_VIEW,
        INVOICES_VIEW,
        DEBTS_VIEW,
        COSTS_VIEW,
        REPORTS_VIEW,
        ALERTS_VIEW,
        COMPANY_FINANCE_VIEW,
        WORKSPACE_ASSETS_ACCESS,
        ASSETS_VIEW,
    }
)

ROLE_PRESET: dict[str, frozenset[str]] = {
    "ADMIN": PRESET_ADMIN,
    "GESTOR": PRESET_GESTOR,
    "CONSULTA": PRESET_CONSULTA,
}
