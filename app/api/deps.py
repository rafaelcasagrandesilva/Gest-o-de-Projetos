from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose.exceptions import ExpiredSignatureError, JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.permission_codes import (
    PRESET_CONSULTA,
    PROJECTS_EDIT,
    PROJECTS_VIEW,
    PROJECTS_VIEW_DETAIL,
    PROJECTS_VIEW_LIST,
    ROLE_PRESET,
    SYSTEM_ADMIN,
    SYSTEM_ALL_PROJECTS,
)
from app.core.scenario import Scenario
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

# Acesso total explícito (emergência / operação) — não substitui RBAC após migração completa.
_SUPERUSER_EMAILS = frozenset(
    {
        "rafael.casagrande@meconsulting.com.br",
    }
)


def _is_superuser_email(user: User) -> bool:
    return (user.email or "").strip().lower() in _SUPERUSER_EMAILS


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


def permission_names_from_user(user: User) -> set[str]:
    """Lê vínculos user_permissions; se a tabela não existir ou houver erro de DB, retorna vazio (usa preset da role)."""
    out: set[str] = set()
    try:
        for up in getattr(user, "user_permissions", []) or []:
            if up.permission:
                out.add(up.permission.name)
    except Exception:
        logger.warning(
            "permission_names_from_user: falha ao ler user_permissions (tabela ausente?).",
            exc_info=True,
        )
    return out


def effective_permission_names(user: User) -> frozenset[str]:
    raw = permission_names_from_user(user)
    if raw:
        return frozenset(raw)
    preset = ROLE_PRESET.get(primary_role_name(user), PRESET_CONSULTA)
    return frozenset(preset)


def user_has_permission(user: User, code: str) -> bool:
    """Verifica permissão por código. Role ADMIN e e-mail superuser têm acesso total às ações."""
    if _is_superuser_email(user):
        return True
    if ROLE_ADMIN in _user_role_names(user):
        return True
    names = effective_permission_names(user)
    if SYSTEM_ADMIN in names:
        return True
    if code in names:
        return True
    if code in (PROJECTS_VIEW_LIST, PROJECTS_VIEW_DETAIL) and PROJECTS_VIEW in names:
        return True
    return False


def user_has_any_permission(user: User, *codes: str) -> bool:
    """True se o usuário tiver qualquer uma das permissões listadas (OR)."""
    return any(user_has_permission(user, c) for c in codes)


def user_sees_all_projects(user: User) -> bool:
    """Escopo global de projetos (independente de project_users)."""
    if _is_superuser_email(user):
        return True
    if ROLE_ADMIN in _user_role_names(user):
        return True
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


def require_permission(*codes: str) -> Callable:
    async def _dep(user: User = Depends(get_current_user)) -> User:
        if not user_has_any_permission(user, *codes):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão.")
        return user

    return _dep


def require_roles(*allowed: str) -> Callable:
    allowed_set = set(allowed)

    async def _dep(user: User = Depends(get_current_user)) -> User:
        role_names = _user_role_names(user)
        if ROLE_ADMIN in role_names:
            return user
        if not role_names.intersection(allowed_set):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão.")
        return user

    return _dep


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user_has_permission(user, SYSTEM_ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Apenas administradores.")
    return user


async def require_admin_role(user: User = Depends(get_current_user)) -> User:
    """Apenas usuário com role ADMIN (exportação de auditoria, operações restritas ao perfil)."""
    if ROLE_ADMIN not in _user_role_names(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Apenas administradores.")
    return user


async def require_gestor_or_admin(user: User = Depends(get_current_user)) -> User:
    if user_has_any_permission(user, SYSTEM_ADMIN, PROJECTS_EDIT):
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão.")


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
