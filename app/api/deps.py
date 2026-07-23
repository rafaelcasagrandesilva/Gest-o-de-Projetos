from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from typing import Literal
from uuid import UUID

from fastapi import Depends, HTTPException, Header, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose.exceptions import ExpiredSignatureError, JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.permission_codes import (
    EXPLICIT_GRANT_ONLY_PERMISSIONS,
    ALERTS_VIEW,
    ASSETS_EDIT,
    ASSETS_VIEW,
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
    expand_permissions,
    FINANCIAL_DASHBOARD_READ,
    INVOICES_EDIT,
    INVOICES_VIEW,
    PAYABLES_EDIT,
    PAYABLES_VIEW,
    PRESET_CONSULTA,
    PROJECTS_CREATE,
    PROJECTS_DELETE,
    PROJECTS_EDIT,
    PROJECTS_VIEW,
    PROJECTS_VIEW_DETAIL,
    PROJECTS_VIEW_LIST,
    RECEIVABLES_EDIT,
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
    INDICATORS_DIRECTOR,
    INDICATORS_VIEW,
    WORKSPACE_ASSETS_ACCESS,
    WORKSPACE_FINANCE_ACCESS,
    WORKSPACE_INDICATORS_ACCESS,
    WORKSPACE_PROJECTS_ACCESS,
)
from app.core.scenario import Scenario
from app.core.session_context import SESSION_VERSION, resolve_workspace_for_user
from app.core.security import decode_token, normalize_token
from app.database.session import get_db
from app.models.user import User
from app.repositories.projects import ProjectRepository
from app.repositories.users import UserRepository


logger = logging.getLogger(__name__)

security_scheme = HTTPBearer(
    scheme_name="Bearer",
    description="JWT. No Swagger, em Authorize informe o token puro ou o valor completo Bearer seguido do token.",
)

ROLE_ADMIN = "ADMIN"
ROLE_GESTOR = "GESTOR"
ROLE_CONSULTA = "CONSULTA"

def is_app_superuser(user: User) -> bool:
    """Fase 1: o BACKDOOR de e-mail superusuário foi REMOVIDO — não há mais bypass por e-mail.

    Todo acesso é explicado exclusivamente pelas permissões do usuário. Para "acesso total", basta o
    usuário possuir todas as permissões. Mantido retornando False por compatibilidade dos chamadores
    (montagem de sessão/rotas), que passam a nunca receber privilégio implícito.
    """
    return False


def _token_from_credentials(credentials: HTTPAuthorizationCredentials) -> str:
    token = credentials.credentials.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token


def _debug_print(msg: str) -> None:
    if settings.auth_debug:
        print(f"[AUTH_DEBUG] {msg}", flush=True)


def primary_role_name(user: User) -> str:
    for link in getattr(user, "roles", []) or []:
        if link.role:
            return link.role.name
    return ROLE_CONSULTA


def _user_permission_deltas(user: User) -> tuple[set[str], set[str]]:
    """Adições (granted=True) e remoções (granted=False) individuais do usuário sobre o(s) perfil(is)."""
    adds: set[str] = set()
    removes: set[str] = set()
    try:
        for up in getattr(user, "user_permissions", []) or []:
            if not up.permission:
                continue
            # Só é REMOÇÃO quando granted é explicitamente False; None/ausente = adição (default).
            if getattr(up, "granted", True) is False:
                removes.add(up.permission.name)
            else:
                adds.add(up.permission.name)
    except Exception:
        logger.warning(
            "_user_permission_deltas: falha ao ler user_permissions (tabela/coluna ausente?).",
            exc_info=True,
        )
    return adds, removes


def permission_names_from_user(user: User) -> set[str]:
    """Permissões concedidas EXPLICITAMENTE ao usuário (adições individuais, granted=True).

    Usado por permissões de concessão explícita (EXPLICIT_GRANT_ONLY_PERMISSIONS) e pela sessão.
    """
    adds, _ = _user_permission_deltas(user)
    return adds


def _db_role_permission_names(user: User) -> set[str] | None:
    """União das permissões de TODOS os perfis do usuário via role_permissions (vínculo vivo).

    Retorna None quando a infraestrutura de role_permissions está ausente (ex.: antes da migration),
    sinalizando fallback para os presets hardcoded — assim nunca se perde/altera o comportamento.
    """
    try:
        out: set[str] = set()
        for link in getattr(user, "roles", []) or []:
            role = getattr(link, "role", None)
            if role is None:
                continue
            for rp in getattr(role, "permissions", []) or []:
                if rp.permission:
                    out.add(rp.permission.name)
        # Sem perfis OU perfil vazio → set() (modelo de deltas: efetivo = adições − remoções).
        # None só no except abaixo (infra de role_permissions ausente) → fallback de preset legado.
        return out
    except Exception:
        logger.warning(
            "_db_role_permission_names: role_permissions indisponível; usando preset (fallback).",
            exc_info=True,
        )
        return None


def _preset_union(user: User) -> frozenset[str]:
    """Fallback: união dos presets hardcoded de todos os perfis do usuário (comportamento legado)."""
    out: set[str] = set()
    for name in _user_role_names(user):
        out |= set(ROLE_PRESET.get(name, PRESET_CONSULTA))
    if not out:
        out |= set(PRESET_CONSULTA)
    return frozenset(out)


def effective_permission_names(user: User) -> frozenset[str]:
    """Efetivo (vínculo vivo) = ∪ permissões dos perfis ∪ adições individuais − remoções individuais.

    Se a tabela role_permissions estiver ausente/indisponível, usa o preset hardcoded como base
    (compatibilidade) — mas ainda aplica os deltas individuais.
    """
    role_perms = _db_role_permission_names(user)
    adds, removes = _user_permission_deltas(user)
    if role_perms is None:
        base = _preset_union(user)
        return frozenset((set(base) | adds) - removes)
    return frozenset((role_perms | adds) - removes)


def user_has_permission(user: User, code: str) -> bool:
    """Verifica permissão por código.

    Fase 1: autorização depende EXCLUSIVAMENTE das permissões concedidas ao usuário (perfil + deltas).
    NÃO há mais atalho por perfil (role ADMIN), por e-mail (superuser) nem por `system.admin` liberando
    funcionalidades de negócio. `system.admin` concede apenas as funcionalidades administrativas do
    sistema, via grafo (`SYSTEM_ADMIN ⇒ users.manage/settings.*`). O perfil ADMIN continua com acesso
    total porque suas permissões (role_permissions) já contêm todos os códigos.
    """
    if code in EXPLICIT_GRANT_ONLY_PERMISSIONS:
        return code in permission_names_from_user(user)
    names = effective_permission_names(user)
    # Fecho transitivo do modelo de verbos (inclui projects.view ⇒ view_list/detail e
    # system.admin ⇒ funcionalidades administrativas do sistema).
    if code in expand_permissions(names):
        return True
    if code == WORKSPACE_PROJECTS_ACCESS and names.intersection(
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
    ):
        return True
    if code == WORKSPACE_FINANCE_ACCESS and names.intersection(
        {
            FINANCIAL_DASHBOARD_READ,
            PAYABLES_VIEW,
            PAYABLES_EDIT,
            RECEIVABLES_VIEW,
            RECEIVABLES_EDIT,
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
    ):
        return True
    if code == WORKSPACE_ASSETS_ACCESS and names.intersection(
        {
            ASSETS_VIEW,
            ASSETS_EDIT,
            SETTINGS_VIEW,
            SETTINGS_EDIT,
        }
    ):
        return True
    if code == WORKSPACE_INDICATORS_ACCESS and names.intersection(
        {
            INDICATORS_VIEW,
            INDICATORS_DIRECTOR,
        }
    ):
        return True
    return False


def user_has_any_permission(user: User, *codes: str) -> bool:
    """True se o usuário tiver qualquer uma das permissões listadas (OR)."""
    return any(user_has_permission(user, c) for c in codes)


def user_sees_all_projects(user: User) -> bool:
    """Escopo global de projetos (independente de project_users).

    Fase 1: só as permissões de sistema `system.admin`/`system.all_projects` concedem visão global —
    sem atalho por role ADMIN nem por e-mail superuser.
    """
    names = effective_permission_names(user)
    return SYSTEM_ADMIN in names or SYSTEM_ALL_PROJECTS in names


async def user_may_use_dashboard_global(*, user: User, db: AsyncSession) -> bool:
    """
    Pode agregar dashboard sem project_id (visão consolidada).
    Inclui quem tem system.all_projects / ADMIN e quem tem vínculo com todos os projetos do sistema.
    """
    if user_sees_all_projects(user):
        return True
    repo = ProjectRepository(db)
    all_ids = await repo.list_all_project_ids()
    linked = await repo.list_project_ids_for_user(user_id=user.id)
    return len(all_ids) > 0 and set(linked) == set(all_ids)


def _user_role_names(user: User) -> set[str]:
    names: set[str] = set()
    for link in getattr(user, "roles", []) or []:
        if link.role:
            names.add(link.role.name)
    return names


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    raw = _token_from_credentials(credentials)
    token = normalize_token(raw)

    try:
        payload = decode_token(token)
    except ExpiredSignatureError as e:
        _debug_print(f"JWT expirado: {e!s}")
        logger.warning("JWT expirado: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except JWTError as e:
        _debug_print(f"decode_token falhou ({type(e).__name__}): {e!s}")
        logger.warning("decode_token falhou: %s\n%s", e, traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou assinatura incorreta.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    _debug_print(f"token (parcial): {token[:24]}... (len={len(token)})")
    _debug_print(f"payload decodificado: {payload}")

    if payload.get("session_version") != SESSION_VERSION:
        _debug_print("token com versão de sessão incompatível")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão expirada por atualização do sistema. Faça login novamente.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    sub_raw = payload.get("sub")
    if sub_raw is None or (isinstance(sub_raw, str) and not sub_raw.strip()):
        _debug_print("claim 'sub' ausente ou vazio")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sem identificador de usuário (sub).",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if isinstance(sub_raw, (bytes, bytearray)):
        sub_str = sub_raw.decode("utf-8", errors="replace").strip()
    else:
        sub_str = sub_raw.strip() if isinstance(sub_raw, str) else str(sub_raw).strip()
    _debug_print(f"user_id (sub) extraído: {sub_str!r}")

    try:
        user_id = UUID(sub_str)
    except ValueError as e:
        _debug_print(f"UUID inválido a partir de sub: {sub_str!r}")
        logger.warning("sub não é UUID válido: %s", sub_str)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token com identificador de usuário inválido.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    repo = UserRepository(db)
    user = await repo.get_with_roles(user_id)
    if not user:
        _debug_print(f"usuário não encontrado no banco: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        _debug_print(f"usuário inativo: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário inativo.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    request.state.user = user
    return user


WorkspaceName = Literal["projects", "finance", "assets", "indicators"]

_WORKSPACE_ACCESS_PERMISSION: dict[str, str] = {
    "projects": WORKSPACE_PROJECTS_ACCESS,
    "finance": WORKSPACE_FINANCE_ACCESS,
    "assets": WORKSPACE_ASSETS_ACCESS,
    "indicators": WORKSPACE_INDICATORS_ACCESS,
}


async def get_current_workspace(
    request: Request,
    workspace: str | None = Query(default=None),
    x_workspace: str | None = Header(default=None, alias="X-Workspace"),
    user: User = Depends(get_current_user),
) -> WorkspaceName:
    """
    Identifica workspace atual sem impactar rotas existentes.

    Ordem de resolução:
    - Query param `?workspace=projects|finance`
    - Header `X-Workspace: projects|finance`
    - Fallback: workspace padrão permitido para o usuário
    """
    raw = (workspace or x_workspace or "").strip().lower()
    resolved = resolve_workspace_for_user(user, raw, is_superuser=is_app_superuser(user))
    request.state.workspace = resolved
    return resolved


def require_workspace_access(workspace: WorkspaceName) -> Callable:
    """
    Dependency opcional para proteger rotas por workspace.
    Não é aplicada em endpoints existentes (migração incremental).
    """

    perm = _WORKSPACE_ACCESS_PERMISSION.get(workspace, WORKSPACE_PROJECTS_ACCESS)

    async def _dep(user: User = Depends(get_current_user)) -> User:
        if not user_has_any_permission(user, perm):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão.")
        return user

    return _dep


def require_permission(*codes: str) -> Callable:
    async def _dep(user: User = Depends(get_current_user)) -> User:
        if not user_has_any_permission(user, *codes):
            effective = sorted(effective_permission_names(user))
            logger.warning(
                "permission_denied user_id=%s email=%s required=%s effective=%s",
                user.id,
                user.email,
                list(codes),
                effective,
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão.")
        return user

    return _dep


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Funcionalidades administrativas do sistema — exige a PERMISSÃO system.admin (não o perfil)."""
    if not user_has_permission(user, SYSTEM_ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Apenas administradores.")
    return user


async def ensure_project_access(*, user: User, project_id: UUID, db: AsyncSession) -> None:
    if user_sees_all_projects(user):
        return
    projects = ProjectRepository(db)
    if await projects.user_has_access(user_id=user.id, project_id=project_id):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado ao projeto.")


async def require_project_access(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    await ensure_project_access(user=user, project_id=project_id, db=db)
    return user


async def get_accessible_project_ids(user: User, db: AsyncSession) -> list[UUID]:
    if user_sees_all_projects(user):
        return await ProjectRepository(db).list_all_project_ids()
    return await ProjectRepository(db).list_project_ids_for_user(user_id=user.id)


async def ensure_user_has_linked_projects(*, user: User, db: AsyncSession) -> None:
    """Usuários sem visão global precisam de ao menos um projeto em project_users para dados escopados."""
    if user_sees_all_projects(user):
        return
    pids = await ProjectRepository(db).list_project_ids_for_user(user_id=user.id)
    if not pids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário sem projetos vinculados. Solicite a um administrador o acesso aos projetos necessários.",
        )


async def get_user_projects(user_id: UUID, db: AsyncSession) -> list[UUID]:
    return await ProjectRepository(db).list_project_ids_for_user(user_id=user_id)


async def assert_may_write_scenario(
    *,
    user: User,
    scenario: str | Scenario,
    db: AsyncSession,
    project_id: UUID | None = None,
) -> None:
    _ = scenario.value if isinstance(scenario, Scenario) else scenario
    if user_has_permission(user, SYSTEM_ADMIN):
        return
    if project_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Informe um projeto para esta operação.",
        )
    await ensure_project_access(user=user, project_id=project_id, db=db)


def default_scenario_for_create(user: User) -> str:
    if user_has_permission(user, SYSTEM_ADMIN):
        return Scenario.REALIZADO.value
    return Scenario.PREVISTO.value
