from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ROLE_ADMIN, get_current_user, require_roles
from app.database.session import get_db
from app.models.user import User
from app.repositories.projects import ProjectRepository
from app.schemas.users import (
    AssignRoleRequest,
    PasswordResetResponse,
    ResetPasswordRequest,
    RoleCreate,
    RoleRead,
    UserCreate,
    UserRead,
    UserUpdate,
)
from app.services.users_service import UsersService


router = APIRouter()


def _user_payload(user: User, *, project_ids: list[UUID]) -> dict:
    role_names = [link.role.name for link in (getattr(user, "roles", []) or []) if getattr(link, "role", None)]
    skip = {"roles", "project_links", "audit_logs"}
    d = {k: v for k, v in user.__dict__.items() if not k.startswith("_") and k not in skip}
    return {**d, "role_names": role_names, "project_ids": project_ids}


async def _to_user_read(db: AsyncSession, user: User) -> UserRead:
    pids = await ProjectRepository(db).list_project_ids_for_user(user_id=user.id)
    return UserRead.model_validate(_user_payload(user, project_ids=pids))


@router.get("/me", response_model=UserRead)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> UserRead:
    return await _to_user_read(db, user)


@router.get("/", response_model=list[UserRead], dependencies=[Depends(require_roles(ROLE_ADMIN))])
async def list_users(
    db: AsyncSession = Depends(get_db),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[UserRead]:
    users = await UsersService(db).list_users(offset=offset, limit=limit)
    out: list[UserRead] = []
    for u in users:
        out.append(await _to_user_read(db, u))
    return out


@router.post("/", response_model=UserRead, dependencies=[Depends(require_roles(ROLE_ADMIN))])
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> UserRead:
    user = await UsersService(db).create_user(
        actor_user_id=actor.id,
        email=payload.email,
        full_name=payload.full_name,
        password=payload.password,
        is_active=payload.is_active,
        role_name=payload.role_name,
        project_ids=payload.project_ids,
    )
    return await _to_user_read(db, user)


@router.post(
    "/{user_id}/reset-password",
    response_model=PasswordResetResponse,
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
async def reset_user_password(
    user_id: UUID,
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> PasswordResetResponse:
    await UsersService(db).reset_password(
        actor_user_id=actor.id, user_id=user_id, new_password=payload.new_password
    )
    return PasswordResetResponse(detail="Senha atualizada com sucesso.")


@router.patch("/{user_id}", response_model=UserRead, dependencies=[Depends(require_roles(ROLE_ADMIN))])
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> UserRead:
    user = await UsersService(db).update_user(
        actor_user_id=actor.id,
        user_id=user_id,
        data=payload.model_dump(exclude_unset=True),
    )
    return await _to_user_read(db, user)


@router.delete("/{user_id}", status_code=204, dependencies=[Depends(require_roles(ROLE_ADMIN))])
async def delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> None:
    await UsersService(db).delete_user(actor_user_id=actor.id, user_id=user_id)


@router.post("/roles", response_model=RoleRead, dependencies=[Depends(require_roles(ROLE_ADMIN))])
async def create_role(
    payload: RoleCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> RoleRead:
    role = await UsersService(db).ensure_role(actor_user_id=actor.id, name=payload.name, description=payload.description)
    return RoleRead.model_validate(role)


@router.post("/{user_id}/roles", status_code=204, dependencies=[Depends(require_roles(ROLE_ADMIN))])
async def assign_role(
    user_id: UUID,
    payload: AssignRoleRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> None:
    await UsersService(db).assign_role(
        actor_user_id=actor.id,
        user_id=user_id,
        role_name=payload.role_name,
        project_ids=payload.project_ids,
    )
