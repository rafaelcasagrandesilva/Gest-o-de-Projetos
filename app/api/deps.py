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


def _token_from_credentials(credentials: HTTPAuthorizationCredentials) -> str:
    token = credentials.credentials.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token


def _debug_print(msg: str) -> None:
    if settings.auth_debug:
        print(f"[AUTH_DEBUG] {msg}", flush=True)


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
    if sub_raw is None:
        _debug_print("claim 'sub' ausente")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sem identificador de usuário (sub).",
            headers={"WWW-Authenticate": "Bearer"},
        )

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


def _user_role_names(user: User) -> set[str]:
    names: set[str] = set()
    for link in getattr(user, "roles", []) or []:
        if link.role:
            names.add(link.role.name)
    return names


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
    if ROLE_ADMIN not in _user_role_names(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Apenas administradores.")
    return user


async def require_gestor_or_admin(user: User = Depends(get_current_user)) -> User:
    names = _user_role_names(user)
    if not (names & {ROLE_ADMIN, ROLE_GESTOR}):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão.")
    return user


async def ensure_project_access(*, user: User, project_id: UUID, db: AsyncSession) -> None:
    """ADMIN/CONSULTA: qualquer projeto; GESTOR: só com vínculo em project_users."""
    role_names = _user_role_names(user)
    if ROLE_ADMIN in role_names or ROLE_CONSULTA in role_names:
        return
    if ROLE_GESTOR in role_names:
        projects = ProjectRepository(db)
        if await projects.user_has_access(user_id=user.id, project_id=project_id):
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado ao projeto.")
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão.")


async def require_project_access(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    await ensure_project_access(user=user, project_id=project_id, db=db)
    return user


async def get_user_projects(user_id: UUID, db: AsyncSession) -> list[UUID]:
    return await ProjectRepository(db).list_project_ids_for_user(user_id=user_id)


async def assert_may_write_scenario(
    *,
    user: User,
    scenario: str | Scenario,
    db: AsyncSession,
    project_id: UUID | None = None,
) -> None:
    """CONSULTA: bloqueia escrita. ADMIN: qualquer cenário (global ou projeto). GESTOR: PREVISTO e REALIZADO apenas com project_id e vínculo ao projeto."""
    _ = scenario.value if isinstance(scenario, Scenario) else scenario  # reservado para regras futuras
    names = _user_role_names(user)
    if ROLE_CONSULTA in names and ROLE_ADMIN not in names:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário somente leitura.",
        )
    if ROLE_ADMIN in names:
        return
    if ROLE_GESTOR in names:
        if project_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Gestores só podem alterar dados em projetos aos quais têm acesso.",
            )
        await ensure_project_access(user=user, project_id=project_id, db=db)
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão.")


def default_scenario_for_create(user: User) -> str:
    """Padrão ao criar sem informar scenario: ADMIN → REALIZADO; demais (ex.: GESTOR) → PREVISTO."""
    if ROLE_ADMIN in _user_role_names(user):
        return Scenario.REALIZADO.value
    return Scenario.PREVISTO.value


async def block_consulta_writes(
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return
    if ROLE_CONSULTA not in _user_role_names(user):
        return
    path = request.url.path
    if request.method == "POST" and "/reports/generate" in path:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Usuário somente leitura",
    )
