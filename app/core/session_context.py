from __future__ import annotations

from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permission_codes import (
    EXPLICIT_GRANT_ONLY_PERMISSIONS,
    ALERTS_VIEW,
    BILLING_VIEW,
    COMPANY_FINANCE_EDIT,
    COMPANY_FINANCE_VIEW,
    COSTS_EDIT,
    COSTS_VIEW,
    DASHBOARD_DIRECTOR,
    DASHBOARD_VIEW,
    DEBTS_EDIT,
    DEBTS_VIEW,
    EMPLOYEES_EDIT,
    EMPLOYEES_VIEW,
    INVOICES_EDIT,
    INVOICES_VIEW,
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
    WORKSPACE_PROJECTS_ACCESS,
)
from app.models.user import User
from app.repositories.projects import ProjectRepository


SESSION_VERSION = 2
WorkspaceName = Literal["projects", "finance", "assets"]

PROJECTS_WORKSPACE_PERMISSIONS = frozenset(
    {
        DASHBOARD_VIEW,
        DASHBOARD_DIRECTOR,
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
        COSTS_VIEW,
        COSTS_EDIT,
        REPORTS_VIEW,
        REPORTS_EXPORT,
        ALERTS_VIEW,
        SETTINGS_VIEW,
        SETTINGS_EDIT,
        USERS_MANAGE,
    }
)

FINANCE_WORKSPACE_PERMISSIONS = frozenset(
    {
        PAYABLES_VIEW,
        RECEIVABLES_VIEW,
        INVOICES_VIEW,
        INVOICES_EDIT,
        DEBTS_VIEW,
        DEBTS_EDIT,
        COMPANY_FINANCE_VIEW,
        COMPANY_FINANCE_EDIT,
        REPORTS_VIEW,
        REPORTS_EXPORT,
        SETTINGS_VIEW,
        SETTINGS_EDIT,
    }
)

ASSETS_WORKSPACE_PERMISSIONS = frozenset(
    {
        ASSETS_VIEW,
        ASSETS_EDIT,
        SETTINGS_VIEW,
        SETTINGS_EDIT,
    }
)


def role_names(user: User) -> list[str]:
    return [link.role.name for link in (getattr(user, "roles", []) or []) if getattr(link, "role", None)]


def role_name_set(user: User) -> set[str]:
    return set(role_names(user))


def primary_role_name(user: User) -> str:
    names = role_names(user)
    return names[0] if names else "CONSULTA"


def permission_names_from_user(user: User) -> set[str]:
    out: set[str] = set()
    for up in getattr(user, "user_permissions", []) or []:
        if up.permission:
            out.add(up.permission.name)
    return out


def effective_permission_names(user: User) -> frozenset[str]:
    raw = permission_names_from_user(user)
    if raw:
        return frozenset(raw)
    return frozenset(ROLE_PRESET.get(primary_role_name(user), PRESET_CONSULTA))


def _workspace_permission_from_module_permissions(names: frozenset[str], code: str) -> bool:
    if code == WORKSPACE_PROJECTS_ACCESS:
        return bool(names.intersection(PROJECTS_WORKSPACE_PERMISSIONS))
    if code == WORKSPACE_FINANCE_ACCESS:
        return bool(names.intersection(FINANCE_WORKSPACE_PERMISSIONS))
    if code == WORKSPACE_ASSETS_ACCESS:
        return bool(names.intersection(ASSETS_WORKSPACE_PERMISSIONS))
    return False


def user_has_permission(user: User, code: str, *, is_superuser: bool = False) -> bool:
    if code in EXPLICIT_GRANT_ONLY_PERMISSIONS:
        return code in permission_names_from_user(user)
    if is_superuser:
        return True
    if "ADMIN" in role_name_set(user):
        return True
    names = effective_permission_names(user)
    if SYSTEM_ADMIN in names:
        return True
    if code in names:
        return True
    if code in (PROJECTS_VIEW_LIST, PROJECTS_VIEW_DETAIL) and PROJECTS_VIEW in names:
        return True
    return _workspace_permission_from_module_permissions(names, code)


def accessible_workspaces(user: User, *, is_superuser: bool = False) -> list[WorkspaceName]:
    out: list[WorkspaceName] = []
    if user_has_permission(user, WORKSPACE_PROJECTS_ACCESS, is_superuser=is_superuser):
        out.append("projects")
    if user_has_permission(user, WORKSPACE_FINANCE_ACCESS, is_superuser=is_superuser):
        out.append("finance")
    if user_has_permission(user, WORKSPACE_ASSETS_ACCESS, is_superuser=is_superuser):
        out.append("assets")
    return out


def session_permission_names(user: User, *, is_superuser: bool = False) -> list[str]:
    names = set(effective_permission_names(user))
    # Garante que permissões explícitas (ex.: invoices.reactivate) apareçam na sessão/frontend.
    names.update(permission_names_from_user(user))
    if user_has_permission(user, WORKSPACE_PROJECTS_ACCESS, is_superuser=is_superuser):
        names.add(WORKSPACE_PROJECTS_ACCESS)
    if user_has_permission(user, WORKSPACE_FINANCE_ACCESS, is_superuser=is_superuser):
        names.add(WORKSPACE_FINANCE_ACCESS)
    if user_has_permission(user, WORKSPACE_ASSETS_ACCESS, is_superuser=is_superuser):
        names.add(WORKSPACE_ASSETS_ACCESS)
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
