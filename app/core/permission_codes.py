"""Códigos de permissão (nome estável em banco e API).

Modelo de verbos (Etapa 0 — infraestrutura). Cada recurso passa a ter permissões em dois eixos:

- Verbo (o que se faz): reference < list < read < create/update/delete
- Sensibilidade (quais campos se recebe): `<recurso>.sensitive` (bundle) e, no futuro, campos
  granulares como `<recurso>.salary`, `<recurso>.documents`, etc.

A hierarquia é resolvida por um GRAFO de implicação declarativo (`PERMISSION_IMPLIES`) cujo fecho
transitivo (`expand_permissions`) é usado tanto por `app/api/deps.py` quanto por
`app/core/session_context.py`. Os códigos legados `<recurso>.view`/`<recurso>.edit` NÃO mudam de
sentido: viram bundles que IMPLICAM os códigos novos equivalentes ao comportamento atual — assim a
compatibilidade é 100% por código, sem migração de `user_permissions`.

NEUTRALIDADE (Etapa 0): os códigos novos nascem INATIVOS (`ACTIVE_PERMISSION_CODES` só contém os
legados). Código inativo não entra na sessão do usuário (`session_permission_names`) e nenhum
endpoint o checa ainda — o deploy é funcionalmente neutro. Cada etapa seguinte "ativa" os códigos
do seu módulo e repoint dos endpoints.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

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
# Modelo de verbos (Fase 2 — Lote B). reference p/ pickers de projeto; sensitive = contrato/margens/PII.
PROJECTS_REFERENCE = "projects.reference"
PROJECTS_LIST = "projects.list"
PROJECTS_READ = "projects.read"
PROJECTS_UPDATE = "projects.update"
PROJECTS_SENSITIVE = "projects.sensitive"
# Documentos do projeto (aba Documentos no modal Detalhes).
PROJECTS_DOCUMENTS_VIEW = "projects.documents.view"
PROJECTS_DOCUMENTS_UPLOAD = "projects.documents.upload"
PROJECTS_DOCUMENTS_DELETE = "projects.documents.delete"

EMPLOYEES_VIEW = "employees.view"
EMPLOYEES_EDIT = "employees.edit"

VEHICLES_VIEW = "vehicles.view"
VEHICLES_EDIT = "vehicles.edit"

BILLING_VIEW = "billing.view"

PAYABLES_VIEW = "payables.view"
# Edição do Contas a Pagar (CAP). Permissão PRÓPRIA do módulo — antes o CAP editava com
# costs.edit (Custos), acoplando os dois. Cada módulo tem seu próprio view/edit.
PAYABLES_EDIT = "payables.edit"
RECEIVABLES_VIEW = "receivables.view"
# Edição do Contas a Receber (itens manuais). Permissão PRÓPRIA — antes editava com invoices.edit.
RECEIVABLES_EDIT = "receivables.edit"
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

# ---------------------------------------------------------------------------
# Verbos dos módulos FINANCEIROS (CRUD) e de LEITURA. Legados *.view/*.edit viram aliases no grafo.
# ---------------------------------------------------------------------------
# Contas a Pagar (CAP)
PAYABLES_LIST = "payables.list"
PAYABLES_READ = "payables.read"
PAYABLES_CREATE = "payables.create"
PAYABLES_UPDATE = "payables.update"
PAYABLES_DELETE = "payables.delete"
PAYABLES_SENSITIVE = "payables.sensitive"
# Contas a Receber (itens manuais)
RECEIVABLES_LIST = "receivables.list"
RECEIVABLES_READ = "receivables.read"
RECEIVABLES_CREATE = "receivables.create"
RECEIVABLES_UPDATE = "receivables.update"
RECEIVABLES_DELETE = "receivables.delete"
RECEIVABLES_SENSITIVE = "receivables.sensitive"
# Notas Fiscais
INVOICES_LIST = "invoices.list"
INVOICES_READ = "invoices.read"
INVOICES_CREATE = "invoices.create"
INVOICES_UPDATE = "invoices.update"
INVOICES_DELETE = "invoices.delete"
INVOICES_SENSITIVE = "invoices.sensitive"
# Endividamento
DEBTS_LIST = "debts.list"
DEBTS_READ = "debts.read"
DEBTS_CREATE = "debts.create"
DEBTS_UPDATE = "debts.update"
DEBTS_DELETE = "debts.delete"
DEBTS_SENSITIVE = "debts.sensitive"
# Custos
COSTS_LIST = "costs.list"
COSTS_READ = "costs.read"
COSTS_CREATE = "costs.create"
COSTS_UPDATE = "costs.update"
COSTS_DELETE = "costs.delete"
COSTS_SENSITIVE = "costs.sensitive"
# Finanças da Empresa (Custos Fixos-Matriz)
COMPANY_FINANCE_LIST = "company_finance.list"
COMPANY_FINANCE_READ = "company_finance.read"
COMPANY_FINANCE_CREATE = "company_finance.create"
COMPANY_FINANCE_UPDATE = "company_finance.update"
COMPANY_FINANCE_DELETE = "company_finance.delete"
COMPANY_FINANCE_SENSITIVE = "company_finance.sensitive"
# Faturamento (receitas) — CRUD.
BILLING_LIST = "billing.list"
BILLING_READ = "billing.read"
BILLING_CREATE = "billing.create"
BILLING_UPDATE = "billing.update"
BILLING_DELETE = "billing.delete"
BILLING_SENSITIVE = "billing.sensitive"
INDICATORS_READ = "indicators.read"
INDICATORS_SENSITIVE = "indicators.sensitive"
DASHBOARD_READ = "dashboard.read"
DASHBOARD_SENSITIVE = "dashboard.sensitive"
# Dashboard Financeiro (Financeiro → Dashboard): recurso PRÓPRIO, espelhando o Dashboard de Projetos
# (`dashboard.read`/`dashboard.sensitive`). `read` = acessar a tela; `sensitive` = receber os valores
# (faturamento/pago/caixa e composições). Antes a tela reusava `billing.read` (Faturamento) e não
# passava por `redact_for` — sem recurso próprio nem gate de dados sensíveis.
FINANCIAL_DASHBOARD_READ = "financial_dashboard.read"
FINANCIAL_DASHBOARD_SENSITIVE = "financial_dashboard.sensitive"
ALERTS_READ = "alerts.read"
REPORTS_READ = "reports.read"
# Configurações (system) — read/update
SETTINGS_READ = "settings.read"
SETTINGS_UPDATE = "settings.update"

# ---------------------------------------------------------------------------
# Modelo de verbos (Etapa 0). Códigos NOVOS — inativos até a etapa do módulo.
# Nomes internos read/update (não view/edit) para não colidir com os legados
# `<recurso>.view`/`<recurso>.edit`, preservando o efetivo atual sem tocar em user_permissions.
# Rótulos em pt-BR ficam no catálogo (PERMISSION_SPECS) — o admin nunca vê read/update.
# ---------------------------------------------------------------------------

# Colaboradores
EMPLOYEES_REFERENCE = "employees.reference"
EMPLOYEES_LIST = "employees.list"
EMPLOYEES_READ = "employees.read"
EMPLOYEES_CREATE = "employees.create"
EMPLOYEES_UPDATE = "employees.update"
EMPLOYEES_DELETE = "employees.delete"
EMPLOYEES_SENSITIVE = "employees.sensitive"
# Exportar do módulo Colaboradores. Regra arquitetural: exportações de um recurso específico usam
# `<recurso>.export` próprio (não `reports.export`, que passa a valer só para o módulo Relatórios).
EMPLOYEES_EXPORT = "employees.export"

# Ativos
ASSETS_REFERENCE = "assets.reference"
ASSETS_LIST = "assets.list"
ASSETS_READ = "assets.read"
ASSETS_CREATE = "assets.create"
ASSETS_UPDATE = "assets.update"
ASSETS_DELETE = "assets.delete"
ASSETS_SENSITIVE = "assets.sensitive"

# Veículos (frota). `sensitive` cobre o campo financeiro monthly_cost.
VEHICLES_REFERENCE = "vehicles.reference"
VEHICLES_LIST = "vehicles.list"
VEHICLES_READ = "vehicles.read"
VEHICLES_CREATE = "vehicles.create"
VEHICLES_UPDATE = "vehicles.update"
VEHICLES_DELETE = "vehicles.delete"
VEHICLES_SENSITIVE = "vehicles.sensitive"
# Exportar do módulo Veículos. Mesmo padrão de employees.export: exportação de recurso específico
# usa `<recurso>.export` próprio (não `reports.export`).
VEHICLES_EXPORT = "vehicles.export"

# Centro de Custo (apenas referência nesta etapa — é vocabulário, não CRUD)
COST_CENTER_REFERENCE = "cost_center.reference"

# Tupla dos códigos introduzidos no modelo de verbos (declarados/atribuíveis; inativos por padrão).
NEW_PERMISSION_CODES: tuple[str, ...] = (
    EMPLOYEES_REFERENCE,
    EMPLOYEES_LIST,
    EMPLOYEES_READ,
    EMPLOYEES_CREATE,
    EMPLOYEES_UPDATE,
    EMPLOYEES_DELETE,
    EMPLOYEES_SENSITIVE,
    EMPLOYEES_EXPORT,
    ASSETS_REFERENCE,
    ASSETS_LIST,
    ASSETS_READ,
    ASSETS_CREATE,
    ASSETS_UPDATE,
    ASSETS_DELETE,
    ASSETS_SENSITIVE,
    VEHICLES_REFERENCE,
    VEHICLES_LIST,
    VEHICLES_READ,
    VEHICLES_CREATE,
    VEHICLES_UPDATE,
    VEHICLES_DELETE,
    VEHICLES_SENSITIVE,
    VEHICLES_EXPORT,
    PROJECTS_REFERENCE,
    PROJECTS_LIST,
    PROJECTS_READ,
    PROJECTS_UPDATE,
    PROJECTS_SENSITIVE,
    PAYABLES_LIST, PAYABLES_READ, PAYABLES_CREATE, PAYABLES_UPDATE, PAYABLES_DELETE, PAYABLES_SENSITIVE,
    RECEIVABLES_LIST, RECEIVABLES_READ, RECEIVABLES_CREATE, RECEIVABLES_UPDATE, RECEIVABLES_DELETE, RECEIVABLES_SENSITIVE,
    INVOICES_LIST, INVOICES_READ, INVOICES_CREATE, INVOICES_UPDATE, INVOICES_DELETE, INVOICES_SENSITIVE,
    DEBTS_LIST, DEBTS_READ, DEBTS_CREATE, DEBTS_UPDATE, DEBTS_DELETE, DEBTS_SENSITIVE,
    COSTS_LIST, COSTS_READ, COSTS_CREATE, COSTS_UPDATE, COSTS_DELETE, COSTS_SENSITIVE,
    COMPANY_FINANCE_LIST, COMPANY_FINANCE_READ, COMPANY_FINANCE_CREATE, COMPANY_FINANCE_UPDATE, COMPANY_FINANCE_DELETE, COMPANY_FINANCE_SENSITIVE,
    BILLING_LIST, BILLING_READ, BILLING_CREATE, BILLING_UPDATE, BILLING_DELETE, BILLING_SENSITIVE,
    INDICATORS_READ, INDICATORS_SENSITIVE,
    DASHBOARD_READ, DASHBOARD_SENSITIVE,
    FINANCIAL_DASHBOARD_READ, FINANCIAL_DASHBOARD_SENSITIVE,
    ALERTS_READ, REPORTS_READ,
    SETTINGS_READ, SETTINGS_UPDATE,
    COST_CENTER_REFERENCE,
)

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
    PROJECTS_DOCUMENTS_VIEW,
    PROJECTS_DOCUMENTS_UPLOAD,
    PROJECTS_DOCUMENTS_DELETE,
    EMPLOYEES_VIEW,
    EMPLOYEES_EDIT,
    VEHICLES_VIEW,
    VEHICLES_EDIT,
    BILLING_VIEW,
    PAYABLES_VIEW,
    PAYABLES_EDIT,
    RECEIVABLES_VIEW,
    RECEIVABLES_EDIT,
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
    # --- Modelo de verbos (Etapa 0) ---
    EMPLOYEES_REFERENCE,
    EMPLOYEES_LIST,
    EMPLOYEES_READ,
    EMPLOYEES_CREATE,
    EMPLOYEES_UPDATE,
    EMPLOYEES_DELETE,
    EMPLOYEES_SENSITIVE,
    EMPLOYEES_EXPORT,
    ASSETS_REFERENCE,
    ASSETS_LIST,
    ASSETS_READ,
    ASSETS_CREATE,
    ASSETS_UPDATE,
    ASSETS_DELETE,
    ASSETS_SENSITIVE,
    VEHICLES_REFERENCE,
    VEHICLES_LIST,
    VEHICLES_READ,
    VEHICLES_CREATE,
    VEHICLES_UPDATE,
    VEHICLES_DELETE,
    VEHICLES_SENSITIVE,
    VEHICLES_EXPORT,
    PROJECTS_REFERENCE,
    PROJECTS_LIST,
    PROJECTS_READ,
    PROJECTS_UPDATE,
    PROJECTS_SENSITIVE,
    PAYABLES_LIST, PAYABLES_READ, PAYABLES_CREATE, PAYABLES_UPDATE, PAYABLES_DELETE, PAYABLES_SENSITIVE,
    RECEIVABLES_LIST, RECEIVABLES_READ, RECEIVABLES_CREATE, RECEIVABLES_UPDATE, RECEIVABLES_DELETE, RECEIVABLES_SENSITIVE,
    INVOICES_LIST, INVOICES_READ, INVOICES_CREATE, INVOICES_UPDATE, INVOICES_DELETE, INVOICES_SENSITIVE,
    DEBTS_LIST, DEBTS_READ, DEBTS_CREATE, DEBTS_UPDATE, DEBTS_DELETE, DEBTS_SENSITIVE,
    COSTS_LIST, COSTS_READ, COSTS_CREATE, COSTS_UPDATE, COSTS_DELETE, COSTS_SENSITIVE,
    COMPANY_FINANCE_LIST, COMPANY_FINANCE_READ, COMPANY_FINANCE_CREATE, COMPANY_FINANCE_UPDATE, COMPANY_FINANCE_DELETE, COMPANY_FINANCE_SENSITIVE,
    BILLING_LIST, BILLING_READ, BILLING_CREATE, BILLING_UPDATE, BILLING_DELETE, BILLING_SENSITIVE,
    INDICATORS_READ, INDICATORS_SENSITIVE,
    DASHBOARD_READ, DASHBOARD_SENSITIVE,
    FINANCIAL_DASHBOARD_READ, FINANCIAL_DASHBOARD_SENSITIVE,
    ALERTS_READ, REPORTS_READ,
    SETTINGS_READ, SETTINGS_UPDATE,
    COST_CENTER_REFERENCE,
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
        FINANCIAL_DASHBOARD_READ,
        FINANCIAL_DASHBOARD_SENSITIVE,
        WORKSPACE_INDICATORS_ACCESS,
        INDICATORS_VIEW,
        INDICATORS_DIRECTOR,
        PROJECTS_VIEW,
        PROJECTS_VIEW_LIST,
        PROJECTS_VIEW_DETAIL,
        PROJECTS_CREATE,
        PROJECTS_EDIT,
        PROJECTS_DELETE,
        PROJECTS_DOCUMENTS_VIEW,
        PROJECTS_DOCUMENTS_UPLOAD,
        PROJECTS_DOCUMENTS_DELETE,
        EMPLOYEES_VIEW,
        EMPLOYEES_EDIT,
        VEHICLES_VIEW,
        VEHICLES_EDIT,
        BILLING_VIEW,
        PAYABLES_VIEW,
        PAYABLES_EDIT,
        RECEIVABLES_VIEW,
        RECEIVABLES_EDIT,
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
        # Modelo de verbos (equivalente a *.edit legado): CRUD completo + sensitive.
        EMPLOYEES_REFERENCE,
        EMPLOYEES_LIST,
        EMPLOYEES_READ,
        EMPLOYEES_CREATE,
        EMPLOYEES_UPDATE,
        EMPLOYEES_DELETE,
        EMPLOYEES_SENSITIVE,
        EMPLOYEES_EXPORT,
        ASSETS_REFERENCE,
        ASSETS_LIST,
        ASSETS_READ,
        ASSETS_CREATE,
        ASSETS_UPDATE,
        ASSETS_DELETE,
        ASSETS_SENSITIVE,
        VEHICLES_REFERENCE,
        VEHICLES_LIST,
        VEHICLES_READ,
        VEHICLES_CREATE,
        VEHICLES_UPDATE,
        VEHICLES_DELETE,
        VEHICLES_SENSITIVE,
        VEHICLES_EXPORT,
        PROJECTS_REFERENCE,
        PROJECTS_LIST,
        PROJECTS_READ,
        PROJECTS_UPDATE,
        PROJECTS_SENSITIVE,
        COST_CENTER_REFERENCE,
    }
)

PRESET_CONSULTA = frozenset(
    {
        WORKSPACE_PROJECTS_ACCESS,
        WORKSPACE_FINANCE_ACCESS,
        DASHBOARD_VIEW,
        FINANCIAL_DASHBOARD_READ,
        FINANCIAL_DASHBOARD_SENSITIVE,
        WORKSPACE_INDICATORS_ACCESS,
        INDICATORS_VIEW,
        PROJECTS_VIEW,
        PROJECTS_VIEW_LIST,
        PROJECTS_VIEW_DETAIL,
        PROJECTS_DOCUMENTS_VIEW,
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
        # Modelo de verbos (equivalente a *.view legado): leitura + sensitive, sem CRUD.
        EMPLOYEES_REFERENCE,
        EMPLOYEES_LIST,
        EMPLOYEES_READ,
        EMPLOYEES_SENSITIVE,
        ASSETS_REFERENCE,
        ASSETS_LIST,
        ASSETS_READ,
        VEHICLES_REFERENCE,
        VEHICLES_LIST,
        VEHICLES_READ,
        VEHICLES_SENSITIVE,
        PROJECTS_REFERENCE,
        PROJECTS_LIST,
        PROJECTS_READ,
        PROJECTS_SENSITIVE,
        COST_CENTER_REFERENCE,
    }
)

ROLE_PRESET: dict[str, frozenset[str]] = {
    "ADMIN": PRESET_ADMIN,
    "GESTOR": PRESET_GESTOR,
    "CONSULTA": PRESET_CONSULTA,
}


# ===========================================================================
# Grafo de implicação + catálogo + fecho transitivo (Etapa 0)
# ===========================================================================

# "A: {B, C}" significa: QUEM TEM A, TEM B e C (implicação direta). O fecho transitivo é calculado
# por `expand_permissions`. Regras:
#   - Cadeia de verbos: update/delete ⇒ read ⇒ list ⇒ reference ; create ⇒ reference.
#   - `sensitive` é independente (bundle; no futuro implicará campos granulares).
#   - Aliases legados: `<r>.view`/`<r>.edit` só apontam para códigos NOVOS (nunca para outro código
#     legado) — assim as consultas por código legado permanecem idênticas (neutralidade E0).
#   - Reproduz o único atalho legado pré-existente: projects.view ⇒ view_list/view_detail.
# Derivação de workspace NÃO entra aqui — continua tratada em session_context (comportamento legado).
PERMISSION_IMPLIES: dict[str, frozenset[str]] = {
    # -- system.admin: APENAS administração do próprio sistema (nunca módulos de negócio). --
    # Deixou de ser "libera tudo" (Fase 1). Concede só as funcionalidades administrativas do sistema.
    SYSTEM_ADMIN: frozenset({USERS_MANAGE, SETTINGS_VIEW, SETTINGS_EDIT}),
    # -- Projetos: verbos + atalho legado (view_list/view_detail) --
    PROJECTS_VIEW: frozenset({PROJECTS_VIEW_LIST, PROJECTS_VIEW_DETAIL, PROJECTS_READ, PROJECTS_SENSITIVE}),
    PROJECTS_EDIT: frozenset({PROJECTS_UPDATE, PROJECTS_SENSITIVE}),
    PROJECTS_UPDATE: frozenset({PROJECTS_READ, COST_CENTER_REFERENCE}),
    PROJECTS_DELETE: frozenset({PROJECTS_READ}),
    PROJECTS_CREATE: frozenset({PROJECTS_REFERENCE, COST_CENTER_REFERENCE}),
    PROJECTS_READ: frozenset({PROJECTS_LIST}),
    PROJECTS_LIST: frozenset({PROJECTS_REFERENCE}),
    # -- Cadeia de verbos: Colaboradores (criar/editar exige escolher Centro de Custo) --
    EMPLOYEES_UPDATE: frozenset({EMPLOYEES_READ, COST_CENTER_REFERENCE}),
    EMPLOYEES_DELETE: frozenset({EMPLOYEES_READ}),
    EMPLOYEES_CREATE: frozenset({EMPLOYEES_REFERENCE, COST_CENTER_REFERENCE}),
    EMPLOYEES_READ: frozenset({EMPLOYEES_LIST}),
    EMPLOYEES_LIST: frozenset({EMPLOYEES_REFERENCE}),
    # -- Cadeia de verbos: Ativos (o ativo tem Centro de Custo) --
    ASSETS_UPDATE: frozenset({ASSETS_READ, COST_CENTER_REFERENCE}),
    ASSETS_DELETE: frozenset({ASSETS_READ}),
    ASSETS_CREATE: frozenset({ASSETS_REFERENCE, COST_CENTER_REFERENCE}),
    ASSETS_READ: frozenset({ASSETS_LIST}),
    ASSETS_LIST: frozenset({ASSETS_REFERENCE}),
    # -- Cadeia de verbos: Veículos (frota tem Centro de Custo; sensitive = monthly_cost) --
    VEHICLES_UPDATE: frozenset({VEHICLES_READ, COST_CENTER_REFERENCE}),
    VEHICLES_DELETE: frozenset({VEHICLES_READ}),
    VEHICLES_CREATE: frozenset({VEHICLES_REFERENCE, COST_CENTER_REFERENCE}),
    VEHICLES_READ: frozenset({VEHICLES_LIST}),
    VEHICLES_LIST: frozenset({VEHICLES_REFERENCE}),
    # -- Aliases legados → códigos NOVOS (compatibilidade sem tocar user_permissions) --
    EMPLOYEES_VIEW: frozenset({EMPLOYEES_READ, EMPLOYEES_SENSITIVE, EMPLOYEES_EXPORT, COST_CENTER_REFERENCE}),
    EMPLOYEES_EDIT: frozenset(
        {EMPLOYEES_CREATE, EMPLOYEES_UPDATE, EMPLOYEES_DELETE, EMPLOYEES_SENSITIVE, EMPLOYEES_EXPORT}
    ),
    ASSETS_VIEW: frozenset({ASSETS_READ, ASSETS_SENSITIVE, COST_CENTER_REFERENCE}),
    ASSETS_EDIT: frozenset({ASSETS_CREATE, ASSETS_UPDATE, ASSETS_DELETE, ASSETS_SENSITIVE}),
    VEHICLES_VIEW: frozenset({VEHICLES_READ, VEHICLES_SENSITIVE, VEHICLES_EXPORT, COST_CENTER_REFERENCE}),
    VEHICLES_EDIT: frozenset({VEHICLES_CREATE, VEHICLES_UPDATE, VEHICLES_DELETE, VEHICLES_SENSITIVE, VEHICLES_EXPORT}),
    # -- Outros legados que já davam acesso a escolher Centro de Custo em selects --
    PROJECTS_VIEW_LIST: frozenset({COST_CENTER_REFERENCE}),
    # -- Módulos financeiros (CRUD): cadeia de verbos + aliases legados view/edit --
    PAYABLES_UPDATE: frozenset({PAYABLES_READ}), PAYABLES_DELETE: frozenset({PAYABLES_READ}),
    PAYABLES_CREATE: frozenset({PAYABLES_READ}), PAYABLES_READ: frozenset({PAYABLES_LIST}),
    PAYABLES_VIEW: frozenset({PAYABLES_READ, PAYABLES_SENSITIVE}),
    PAYABLES_EDIT: frozenset({PAYABLES_CREATE, PAYABLES_UPDATE, PAYABLES_DELETE, PAYABLES_SENSITIVE}),
    RECEIVABLES_UPDATE: frozenset({RECEIVABLES_READ}), RECEIVABLES_DELETE: frozenset({RECEIVABLES_READ}),
    RECEIVABLES_CREATE: frozenset({RECEIVABLES_READ}), RECEIVABLES_READ: frozenset({RECEIVABLES_LIST}),
    RECEIVABLES_VIEW: frozenset({RECEIVABLES_READ, RECEIVABLES_SENSITIVE}),
    RECEIVABLES_EDIT: frozenset({RECEIVABLES_CREATE, RECEIVABLES_UPDATE, RECEIVABLES_DELETE, RECEIVABLES_SENSITIVE}),
    INVOICES_UPDATE: frozenset({INVOICES_READ}), INVOICES_DELETE: frozenset({INVOICES_READ}),
    INVOICES_CREATE: frozenset({INVOICES_READ}), INVOICES_READ: frozenset({INVOICES_LIST}),
    INVOICES_VIEW: frozenset({INVOICES_READ, INVOICES_SENSITIVE}),
    INVOICES_EDIT: frozenset({INVOICES_CREATE, INVOICES_UPDATE, INVOICES_DELETE, INVOICES_SENSITIVE}),
    DEBTS_UPDATE: frozenset({DEBTS_READ}), DEBTS_DELETE: frozenset({DEBTS_READ}),
    DEBTS_CREATE: frozenset({DEBTS_READ}), DEBTS_READ: frozenset({DEBTS_LIST}),
    DEBTS_VIEW: frozenset({DEBTS_READ, DEBTS_SENSITIVE}),
    DEBTS_EDIT: frozenset({DEBTS_CREATE, DEBTS_UPDATE, DEBTS_DELETE, DEBTS_SENSITIVE}),
    COSTS_UPDATE: frozenset({COSTS_READ}), COSTS_DELETE: frozenset({COSTS_READ}),
    COSTS_CREATE: frozenset({COSTS_READ}), COSTS_READ: frozenset({COSTS_LIST}),
    COSTS_VIEW: frozenset({COSTS_READ, COSTS_SENSITIVE}),
    COSTS_EDIT: frozenset({COSTS_CREATE, COSTS_UPDATE, COSTS_DELETE, COSTS_SENSITIVE}),
    COMPANY_FINANCE_UPDATE: frozenset({COMPANY_FINANCE_READ}), COMPANY_FINANCE_DELETE: frozenset({COMPANY_FINANCE_READ}),
    COMPANY_FINANCE_CREATE: frozenset({COMPANY_FINANCE_READ}), COMPANY_FINANCE_READ: frozenset({COMPANY_FINANCE_LIST}),
    COMPANY_FINANCE_VIEW: frozenset({COMPANY_FINANCE_READ, COMPANY_FINANCE_SENSITIVE, COST_CENTER_REFERENCE}),
    COMPANY_FINANCE_EDIT: frozenset({COMPANY_FINANCE_CREATE, COMPANY_FINANCE_UPDATE, COMPANY_FINANCE_DELETE, COMPANY_FINANCE_SENSITIVE}),
    # -- Módulos de leitura: view ⇒ read (+ sensitive onde há valores) --
    BILLING_UPDATE: frozenset({BILLING_READ}), BILLING_DELETE: frozenset({BILLING_READ}),
    BILLING_CREATE: frozenset({BILLING_READ}), BILLING_READ: frozenset({BILLING_LIST}),
    BILLING_VIEW: frozenset({BILLING_READ, BILLING_SENSITIVE}),
    INDICATORS_VIEW: frozenset({INDICATORS_READ, INDICATORS_SENSITIVE}),
    DASHBOARD_VIEW: frozenset({DASHBOARD_READ, DASHBOARD_SENSITIVE}),
    ALERTS_VIEW: frozenset({ALERTS_READ}),
    REPORTS_VIEW: frozenset({REPORTS_READ}),
    SETTINGS_VIEW: frozenset({SETTINGS_READ}),
    SETTINGS_EDIT: frozenset({SETTINGS_UPDATE, SETTINGS_READ}),
}


def expand_permissions(held: Iterable[str]) -> frozenset[str]:
    """Fecho transitivo de `held` sob `PERMISSION_IMPLIES` (inclui os próprios códigos de entrada)."""
    seen: set[str] = set(held)
    stack: list[str] = list(seen)
    while stack:
        cur = stack.pop()
        for nxt in PERMISSION_IMPLIES.get(cur, ()):  # type: ignore[arg-type]
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return frozenset(seen)


# Códigos NOVOS já ATIVADOS por etapa (enforçados por endpoint + expostos na sessão).
# Etapa 1/2: pickers (employees.reference, cost_center.reference) + criação de colaborador
# (employees.create — botão "Novo colaborador" e POST /employees deixam de depender de perfil/edit).
# Os demais códigos novos seguem inativos até a etapa do seu módulo.
_ACTIVATED_NEW_CODES: frozenset[str] = frozenset(
    {
        COST_CENTER_REFERENCE,
        # Fase 2 — Lote A (Colaboradores, Ativos, Veículos): verbos CRUD. `*.sensitive` fica na Fase 4.
        EMPLOYEES_REFERENCE, EMPLOYEES_LIST, EMPLOYEES_READ,
        EMPLOYEES_CREATE, EMPLOYEES_UPDATE, EMPLOYEES_DELETE,
        # Fase Dados Sensíveis — Colaboradores: sensitive + export ATIVADOS (adequação funcional do módulo).
        EMPLOYEES_SENSITIVE, EMPLOYEES_EXPORT,
        ASSETS_REFERENCE, ASSETS_LIST, ASSETS_READ,
        ASSETS_CREATE, ASSETS_UPDATE, ASSETS_DELETE,
        # Fase Dados Sensíveis — Ativos: sensitive ATIVADO (omissão dos valores monetários).
        ASSETS_SENSITIVE,
        VEHICLES_REFERENCE, VEHICLES_LIST, VEHICLES_READ,
        VEHICLES_CREATE, VEHICLES_UPDATE, VEHICLES_DELETE,
        # Fase Dados Sensíveis — Veículos: sensitive + export ATIVADOS (adequação funcional do módulo).
        VEHICLES_SENSITIVE, VEHICLES_EXPORT,
        # Fase 2 — Lote B (Projetos). `*.sensitive` fica INATIVO até a Fase 4 (omissão no backend).
        PROJECTS_REFERENCE, PROJECTS_LIST, PROJECTS_READ, PROJECTS_UPDATE,
        # Financeiro (CRUD).
        PAYABLES_LIST, PAYABLES_READ, PAYABLES_CREATE, PAYABLES_UPDATE, PAYABLES_DELETE,
        RECEIVABLES_LIST, RECEIVABLES_READ, RECEIVABLES_CREATE, RECEIVABLES_UPDATE, RECEIVABLES_DELETE,
        INVOICES_LIST, INVOICES_READ, INVOICES_CREATE, INVOICES_UPDATE, INVOICES_DELETE,
        DEBTS_LIST, DEBTS_READ, DEBTS_CREATE, DEBTS_UPDATE, DEBTS_DELETE,
        COSTS_LIST, COSTS_READ, COSTS_CREATE, COSTS_UPDATE, COSTS_DELETE,
        COMPANY_FINANCE_LIST, COMPANY_FINANCE_READ, COMPANY_FINANCE_CREATE, COMPANY_FINANCE_UPDATE, COMPANY_FINANCE_DELETE,
        # Leitura/visão.
        BILLING_LIST, BILLING_READ, BILLING_CREATE, BILLING_UPDATE, BILLING_DELETE,
        INDICATORS_READ, DASHBOARD_READ, ALERTS_READ, REPORTS_READ,
        # Dados Sensíveis — Dashboard Financeiro: recurso próprio ATIVADO (gate de acesso + redação).
        FINANCIAL_DASHBOARD_READ, FINANCIAL_DASHBOARD_SENSITIVE,
        SETTINGS_READ, SETTINGS_UPDATE,
    }
)

# Códigos ATIVOS = expostos na sessão e checados por endpoints. Legados + códigos novos já ativados.
# À medida que cada módulo migra, seus códigos novos entram em `_ACTIVATED_NEW_CODES`.
ACTIVE_PERMISSION_CODES: frozenset[str] = frozenset(
    c for c in ALL_PERMISSION_CODES if c not in NEW_PERMISSION_CODES or c in _ACTIVATED_NEW_CODES
)


@dataclass(frozen=True)
class PermissionSpec:
    """Metadado de UM código novo (para a grade de administração e a documentação)."""

    code: str
    resource: str  # chave do recurso (employees, assets, cost_center)
    verb: str  # reference | list | read | create | update | delete | sensitive
    label: str  # rótulo pt-BR exibido ao admin
    description: str
    active: bool  # exposto/enforçado? (False na Etapa 0)


# Rótulo pt-BR de cada recurso (cabeçalho de grupo na grade).
RESOURCE_LABELS: dict[str, str] = {
    "employees": "Colaboradores",
    "assets": "Ativos",
    "vehicles": "Veículos",
    "projects": "Projetos",
    "cost_center": "Centro de Custo",
}

# Rótulo pt-BR de cada verbo (coluna da grade).
VERB_LABELS: dict[str, str] = {
    "reference": "Referenciar",
    "list": "Listar",
    "read": "Visualizar",
    "create": "Criar",
    "update": "Editar",
    "delete": "Excluir",
    "export": "Exportar",
    "sensitive": "Dados sensíveis",
}

_VERB_ORDER = ("reference", "list", "read", "create", "update", "delete", "export", "sensitive")


def _spec(resource: str, verb: str, description: str) -> PermissionSpec:
    code = f"{resource}.{verb}"
    return PermissionSpec(
        code=code,
        resource=resource,
        verb=verb,
        label=f"{RESOURCE_LABELS[resource]} · {VERB_LABELS[verb]}",
        description=description,
        active=code in ACTIVE_PERMISSION_CODES,
    )


# Catálogo dos códigos NOVOS (fonte para docs e paridade com o frontend).
PERMISSION_SPECS: tuple[PermissionSpec, ...] = (
    _spec("employees", "reference", "Usar um colaborador em seletor/autocomplete (id + nome), sem abrir a tela de Colaboradores."),
    _spec("employees", "list", "Ver a relação de colaboradores SEM campos sensíveis (salário, custos, encargos, PIX)."),
    _spec("employees", "read", "Ver o detalhe de um colaborador SEM campos sensíveis."),
    _spec("employees", "create", "Inserir um novo colaborador."),
    _spec("employees", "update", "Editar um colaborador existente."),
    _spec("employees", "delete", "Inativar/remover um colaborador."),
    _spec("employees", "export", "Exportar o relatório de Colaboradores/Folha (valores financeiros só com Dados sensíveis)."),
    _spec("employees", "sensitive", "Receber os campos sensíveis do colaborador: salário, custos, encargos, total, PIX."),
    _spec("assets", "reference", "Usar um ativo em seletor/autocomplete."),
    _spec("assets", "list", "Ver a relação de ativos SEM campos monetários sensíveis."),
    _spec("assets", "read", "Ver o detalhe de um ativo SEM campos monetários sensíveis."),
    _spec("assets", "create", "Inserir um novo ativo."),
    _spec("assets", "update", "Editar um ativo existente."),
    _spec("assets", "delete", "Remover um ativo."),
    _spec("assets", "sensitive", "Receber os campos monetários do ativo (valor de aquisição/contábil)."),
    _spec("vehicles", "reference", "Usar um veículo em seletor/autocomplete."),
    _spec("vehicles", "list", "Ver a relação de veículos SEM o custo mensal."),
    _spec("vehicles", "read", "Ver o detalhe de um veículo SEM o custo mensal."),
    _spec("vehicles", "create", "Inserir um novo veículo."),
    _spec("vehicles", "update", "Editar um veículo existente."),
    _spec("vehicles", "delete", "Remover um veículo."),
    _spec("vehicles", "export", "Exportar o relatório de Veículos/Frota (valores financeiros só com Dados sensíveis)."),
    _spec("vehicles", "sensitive", "Receber o campo financeiro do veículo (custo mensal)."),
    _spec("projects", "reference", "Usar um projeto em seletor/autocomplete."),
    _spec("projects", "list", "Ver a relação de projetos SEM valores de contrato/margem."),
    _spec("projects", "read", "Ver o detalhe do projeto SEM valores de contrato/margem."),
    _spec("projects", "update", "Editar um projeto existente."),
    _spec("projects", "sensitive", "Receber valores do projeto (contrato, margem) e dados do comprador."),
    _spec("cost_center", "reference", "Escolher um Centro de Custo em seletores, sem acesso à gestão financeira."),
)

