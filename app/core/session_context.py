from __future__ import annotations

from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permission_codes import (
    ACTIVE_PERMISSION_CODES,
    EXPLICIT_GRANT_ONLY_PERMISSIONS,
    expand_permissions,
    workspace_required_for,
    ALERTS_VIEW,
    BILLING_VIEW,
    COMPANY_FINANCE_EDIT,
    COMPANY_FINANCE_VIEW,
    COMPANY_RESULT_READ,
    COSTS_EDIT,
    COSTS_VIEW,
    DASHBOARD_DIRECTOR,
    DASHBOARD_VIEW,
    DEBTS_EDIT,
    DEBTS_VIEW,
    EMPLOYEES_EDIT,
    EMPLOYEES_VIEW,
    FINANCIAL_DASHBOARD_READ,
    INDICATORS_DIRECTOR,
    INDICATORS_VIEW,
    INVOICES_EDIT,
    INVOICES_VIEW,
    LEGAL_WORKSPACE_GRANTING,
    PAYABLES_VIEW,
    PRESET_CONSULTA,
    PROJECTS_CREATE,
    PROJECTS_DELETE,
    PROJECTS_EDIT,
    PROJECTS_VIEW,
    PROJECTS_VIEW_DETAIL,
    PROJECTS_VIEW_LIST,
    RECEIVABLES_VIEW,
    REPORTS_EXPORT,
    REPORTS_VIEW,
    ROLE_PRESET,
    SETTINGS_EDIT,
    SETTINGS_VIEW,
    SYSTEM_ADMIN,
    SYSTEM_ALL_PROJECTS,
    USERS_MANAGE,
    VEHICLES_EDIT,
    VEHICLES_VIEW,
    ASSETS_EDIT,
    ASSETS_VIEW,
    WORKSPACE_ASSETS_ACCESS,
    WORKSPACE_FINANCE_ACCESS,
    WORKSPACE_INDICATORS_ACCESS,
    WORKSPACE_LEGAL_ACCESS,
    WORKSPACE_PROJECTS_ACCESS,
)
from app.models.user import User
from app.repositories.projects import ProjectRepository


SESSION_VERSION = 2
WorkspaceName = Literal["projects", "finance", "assets", "indicators", "legal"]

# Acesso a workspace: SÓ o `workspace.*.access` concedido (perfil/adição − remoção). Não é mais deduzido
# das permissões dos menus — a dedução ignorava o "Acessar" desmarcado (migration 0144 tornou explícito
# o acesso de quem o tinha por dedução).


def role_names(user: User) -> list[str]:
    return [link.role.name for link in (getattr(user, "roles", []) or []) if getattr(link, "role", None)]


def primary_role_name(user: User) -> str:
    names = role_names(user)
    return names[0] if names else "CONSULTA"


def _user_permission_deltas(user: User) -> tuple[set[str], set[str]]:
    """Adições (granted=True) e remoções (granted=False) individuais sobre o(s) perfil(is)."""
    adds: set[str] = set()
    removes: set[str] = set()
    for up in getattr(user, "user_permissions", []) or []:
        if not up.permission:
            continue
        if getattr(up, "granted", True) is False:
            removes.add(up.permission.name)
        else:
            adds.add(up.permission.name)
    return adds, removes


def permission_names_from_user(user: User) -> set[str]:
    """Permissões concedidas EXPLICITAMENTE (adições individuais, granted=True)."""
    adds, _ = _user_permission_deltas(user)
    return adds


def _db_role_permission_names(user: User) -> set[str] | None:
    """União das permissões de TODOS os perfis do usuário via role_permissions (vínculo vivo).
    None só quando a infra de role_permissions está ausente (fallback de preset legado)."""
    try:
        out: set[str] = set()
        for link in getattr(user, "roles", []) or []:
            role = getattr(link, "role", None)
            if role is None:
                continue
            for rp in getattr(role, "permissions", []) or []:
                if rp.permission:
                    out.add(rp.permission.name)
        return out
    except Exception:
        return None


def effective_permission_names(user: User) -> frozenset[str]:
    """Efetivo = ∪ permissões dos perfis ∪ adições individuais − remoções individuais.
    Mesma regra usada na autorização (app/api/deps.py) — SEM somar ROLE_PRESET quando há perfis.
    ROLE_PRESET só é fallback se a tabela role_permissions estiver ausente (infra pré-0091)."""
    role_perms = _db_role_permission_names(user)
    adds, removes = _user_permission_deltas(user)
    if role_perms is None:
        base: set[str] = set()
        for name in role_names(user):
            base |= set(ROLE_PRESET.get(name, PRESET_CONSULTA))
        return frozenset((base | adds) - removes)
    return frozenset((role_perms | adds) - removes)


def user_has_permission(user: User, code: str, *, is_superuser: bool = False) -> bool:
    # Mesma regra de app/api/deps.user_has_permission. Sem atalho por perfil (ADMIN), por e-mail
    # (is_superuser) nem por system.admin liberando negócio — `is_superuser` fica na assinatura só por
    # compat dos chamadores. Workspace só concedido; recurso exclusivo exige o acesso ao workspace dele.
    names = expand_permissions(effective_permission_names(user))
    if code in EXPLICIT_GRANT_ONLY_PERMISSIONS:
        granted = code in permission_names_from_user(user)
    else:
        granted = code in names
    if not granted:
        return False
    workspace = workspace_required_for(code)
    return workspace is None or workspace in names


def accessible_workspaces(user: User, *, is_superuser: bool = False) -> list[WorkspaceName]:
    out: list[WorkspaceName] = []
    if user_has_permission(user, WORKSPACE_PROJECTS_ACCESS, is_superuser=is_superuser):
        out.append("projects")
    if user_has_permission(user, WORKSPACE_FINANCE_ACCESS, is_superuser=is_superuser):
        out.append("finance")
    if user_has_permission(user, WORKSPACE_ASSETS_ACCESS, is_superuser=is_superuser):
        out.append("assets")
    if user_has_permission(user, WORKSPACE_INDICATORS_ACCESS, is_superuser=is_superuser):
        out.append("indicators")
    if user_has_permission(user, WORKSPACE_LEGAL_ACCESS, is_superuser=is_superuser):
        out.append("legal")
    return out


def session_permission_names(user: User, *, is_superuser: bool = False) -> list[str]:
    names = set(effective_permission_names(user))
    # Garante que permissões explícitas (ex.: invoices.reactivate) apareçam na sessão/frontend.
    names.update(permission_names_from_user(user))
    # NEUTRALIDADE: expõe ao frontend apenas códigos ATIVOS. Os códigos novos (modelo de verbos)
    # já podem estar semeados nos perfis, mas não entram na sessão até a etapa que ativa o módulo.
    names &= ACTIVE_PERMISSION_CODES
    # Sem o acesso ao workspace, as permissões dos recursos exclusivos dele não chegam à tela
    # (menus e botões somem junto com o workspace).
    granted = expand_permissions(effective_permission_names(user))
    names = {n for n in names if (ws := workspace_required_for(n)) is None or ws in granted}
    if user_has_permission(user, WORKSPACE_PROJECTS_ACCESS, is_superuser=is_superuser):
        names.add(WORKSPACE_PROJECTS_ACCESS)
    if user_has_permission(user, WORKSPACE_FINANCE_ACCESS, is_superuser=is_superuser):
        names.add(WORKSPACE_FINANCE_ACCESS)
    if user_has_permission(user, WORKSPACE_ASSETS_ACCESS, is_superuser=is_superuser):
        names.add(WORKSPACE_ASSETS_ACCESS)
    if user_has_permission(user, WORKSPACE_INDICATORS_ACCESS, is_superuser=is_superuser):
        names.add(WORKSPACE_INDICATORS_ACCESS)
    if user_has_permission(user, WORKSPACE_LEGAL_ACCESS, is_superuser=is_superuser):
        names.add(WORKSPACE_LEGAL_ACCESS)
    return sorted(names)


def default_workspace_for_user(user: User, *, is_superuser: bool = False) -> WorkspaceName:
    workspaces = accessible_workspaces(user, is_superuser=is_superuser)
    if "projects" in workspaces:
        return "projects"
    if "finance" in workspaces:
        return "finance"
    if "assets" in workspaces:
        return "assets"
    return "projects"


def resolve_workspace_for_user(
    user: User,
    requested: str | None,
    *,
    is_superuser: bool = False,
) -> WorkspaceName:
    requested_norm = (requested or "").strip().lower()
    allowed = accessible_workspaces(user, is_superuser=is_superuser)
    if requested_norm in allowed:
        return requested_norm  # type: ignore[return-value]
    return default_workspace_for_user(user, is_superuser=is_superuser)


async def linked_project_ids(user_id: UUID, db: AsyncSession) -> list[UUID]:
    return await ProjectRepository(db).list_project_ids_for_user(user_id=user_id)


async def build_session_claims(
    *,
    user: User,
    db: AsyncSession,
    requested_workspace: str | None = None,
    is_superuser: bool = False,
) -> dict:
    project_ids = await linked_project_ids(user.id, db)
    default_workspace = default_workspace_for_user(user, is_superuser=is_superuser)
    current_workspace = resolve_workspace_for_user(
        user,
        requested_workspace or default_workspace,
        is_superuser=is_superuser,
    )
    return {
        "session_version": SESSION_VERSION,
        "workspace": current_workspace,
        "current_workspace": current_workspace,
        "default_workspace": default_workspace,
        "roles": role_names(user),
        "permissions": session_permission_names(user, is_superuser=is_superuser),
        "linked_projects": [str(pid) for pid in project_ids],
    }
