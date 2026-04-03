from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ROLE_ADMIN, ROLE_CONSULTA, ROLE_GESTOR
from app.core.security import PasswordHashingError, hash_password
from app.models.user import ProjectUser, Role, User, UserRole
from app.repositories.projects import ProjectRepository
from app.repositories.users import RoleRepository, UserRepository
from app.services.audit_service import AuditService
from app.services.utils import model_to_dict

_VALID_ROLES = frozenset({ROLE_ADMIN, ROLE_GESTOR, ROLE_CONSULTA})

_HASH_FAIL = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="Não foi possível processar a senha neste momento.",
)


def _hash_password_or_http(password: str) -> str:
    try:
        return hash_password(password)
    except PasswordHashingError:
        raise _HASH_FAIL from None


def _primary_role_name(user: User) -> str:
    for link in getattr(user, "roles", []) or []:
        if link.role:
            return link.role.name
    return ROLE_CONSULTA


class UsersService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = UserRepository(session)
        self.roles = RoleRepository(session)
        self.audit = AuditService(session)

    async def list_users(self, *, offset: int = 0, limit: int = 50) -> list[User]:
        return await self.users.list(offset=offset, limit=limit)

    async def get_user(self, user_id) -> User:
        user = await self.users.get_with_roles(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
        return user

    async def _apply_role_and_projects(
        self,
        *,
        user_id: UUID,
        role_name: str,
        project_ids: list[UUID] | None,
    ) -> None:
        if role_name not in _VALID_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Role inválida. Use ADMIN, GESTOR ou CONSULTA.",
            )
        role = await self.roles.get_by_name(role_name)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role não encontrada.")
        await self.session.execute(delete(UserRole).where(UserRole.user_id == user_id))
        await self.session.execute(delete(ProjectUser).where(ProjectUser.user_id == user_id))
        self.session.add(UserRole(user_id=user_id, role_id=role.id))
        if role_name == ROLE_GESTOR and project_ids is not None:
            for pid in project_ids:
                self.session.add(ProjectUser(project_id=pid, user_id=user_id, access_level="member"))
        await self.session.flush()

    async def create_user(
        self,
        *,
        actor_user_id,
        email: str,
        full_name: str,
        password: str,
        is_active: bool,
        role_name: str = ROLE_CONSULTA,
        project_ids: list[UUID] | None = None,
    ) -> User:
        if await self.users.get_by_email(email):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email já cadastrado.")
        user = User(email=email, full_name=full_name, password_hash=_hash_password_or_http(password), is_active=is_active)
        await self.users.add(user)
        await self.session.flush()
        if role_name == ROLE_GESTOR:
            pids: list[UUID] | None = list(project_ids or [])
        else:
            pids = None
        await self._apply_role_and_projects(user_id=user.id, role_name=role_name, project_ids=pids)
        await self.audit.log(
            actor_user_id=actor_user_id,
            action="create",
            entity="User",
            entity_id=user.id,
            before=None,
            after=model_to_dict(user),
        )
        await self.session.commit()
        reloaded = await self.users.get_with_roles(user.id)
        if not reloaded:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
        return reloaded

    async def update_user(self, *, actor_user_id, user_id, data: dict) -> User:
        role_name = data.pop("role_name", None)
        project_ids = data.pop("project_ids", None)
        user = await self.users.get(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
        before = model_to_dict(user)
        if "password" in data and data["password"]:
            user.password_hash = _hash_password_or_http(data.pop("password"))
        self.users.apply_updates(user, data)
        if role_name is not None or project_ids is not None:
            u_roles = await self.users.get_with_roles(user_id)
            if not u_roles:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
            rn = role_name if role_name is not None else _primary_role_name(u_roles)
            if project_ids is not None:
                pids = project_ids
            elif rn == ROLE_GESTOR:
                pids = await ProjectRepository(self.session).list_project_ids_for_user(user_id=user_id)
            else:
                pids = None
            await self._apply_role_and_projects(user_id=user_id, role_name=rn, project_ids=pids)
        await self.audit.log(
            actor_user_id=actor_user_id,
            action="update",
            entity="User",
            entity_id=user.id,
            before=before,
            after=model_to_dict(user),
        )
        await self.session.commit()
        reloaded = await self.users.get_with_roles(user_id)
        if not reloaded:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
        return reloaded

    async def reset_password(self, *, actor_user_id, user_id, new_password: str) -> User:
        user = await self.users.get(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
        before = model_to_dict(user)
        before["password_hash"] = "[redacted]"
        user.password_hash = _hash_password_or_http(new_password)
        await self.session.flush()
        after = model_to_dict(user)
        after["password_hash"] = "[redacted]"
        await self.audit.log(
            actor_user_id=actor_user_id,
            action="reset_password",
            entity="User",
            entity_id=user.id,
            before=before,
            after=after,
        )
        await self.session.commit()
        reloaded = await self.users.get_with_roles(user_id)
        if not reloaded:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
        return reloaded

    async def delete_user(self, *, actor_user_id, user_id) -> None:
        user = await self.users.get(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
        before = model_to_dict(user)
        await self.users.delete(user)
        await self.audit.log(
            actor_user_id=actor_user_id,
            action="delete",
            entity="User",
            entity_id=user_id,
            before=before,
            after=None,
        )
        await self.session.commit()

    async def ensure_role(self, *, actor_user_id, name: str, description: str | None = None) -> Role:
        role = await self.roles.get_by_name(name)
        if role:
            return role
        role = Role(name=name, description=description)
        await self.roles.add(role)
        await self.audit.log(
            actor_user_id=actor_user_id,
            action="create",
            entity="Role",
            entity_id=role.id,
            before=None,
            after=model_to_dict(role),
        )
        await self.session.commit()
        await self.session.refresh(role)
        return role

    async def assign_role(
        self,
        *,
        actor_user_id,
        user_id,
        role_name: str,
        project_ids: list[UUID] | None = None,
    ) -> None:
        user = await self.users.get(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
        pids: list[UUID] | None
        if role_name == ROLE_GESTOR:
            pids = list(project_ids or [])
        else:
            pids = None
        await self._apply_role_and_projects(user_id=user.id, role_name=role_name, project_ids=pids)
        await self.audit.log(
            actor_user_id=actor_user_id,
            action="assign_role",
            entity="User",
            entity_id=user.id,
            before=None,
            after={"role_name": role_name, "project_ids": project_ids},
        )
        await self.session.commit()
