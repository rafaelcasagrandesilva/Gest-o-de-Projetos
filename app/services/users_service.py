from __future__ import annotations

import logging
from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ROLE_ADMIN, ROLE_CONSULTA, ROLE_GESTOR
from app.core.permission_codes import PRESET_CONSULTA, ROLE_PRESET
from app.core.security import PasswordHashingError, hash_password
from app.models.user import ProjectUser, Role, User, UserRole
from app.repositories.permissions import PermissionRepository
from app.repositories.projects import ProjectRepository
from app.repositories.users import RoleRepository, UserRepository
from app.services.audit_service import AuditService
from app.services.utils import model_to_dict

_VALID_ROLES = frozenset({ROLE_ADMIN, ROLE_GESTOR, ROLE_CONSULTA})

logger = logging.getLogger(__name__)

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
        apply_permission_preset: bool = True,
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
        if project_ids is not None:
            for pid in project_ids:
                self.session.add(ProjectUser(project_id=pid, user_id=user_id, access_level="member"))
        await self.session.flush()
        if apply_permission_preset:
            preset = ROLE_PRESET.get(role_name, PRESET_CONSULTA)
            try:
                await PermissionRepository(self.session).replace_user_permissions(user_id, set(preset))
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

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
        actor: User | None = None,
        request: Request | None = None,
    ) -> User:
        if await self.users.get_by_email(email):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email já cadastrado.")
        user = User(email=email, full_name=full_name, password_hash=_hash_password_or_http(password), is_active=is_active)
        await self.users.add(user)
        await self.session.flush()
        pids: list[UUID] | None = list(dict.fromkeys(project_ids or [])) if project_ids is not None else None
        await self._apply_role_and_projects(
            user_id=user.id, role_name=role_name, project_ids=pids, apply_permission_preset=True
        )
        await self.audit.log_action(
            user=actor,
            action="create",
            entity="user",
            entity_id=user.id,
            before=None,
            after=model_to_dict(user),
            context={
                "descricao": "Cadastro de usuário e perfil",
                "email": user.email,
                "role_name": role_name,
            },
            request=request,
        )
        await self.session.commit()
        reloaded = await self.users.get_with_roles(user.id)
        if not reloaded:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
        return reloaded

    async def update_user(
        self,
        *,
        actor_user_id,
        user_id,
        data: dict,
        actor: User | None = None,
        request: Request | None = None,
    ) -> User:
        role_name = data.pop("role_name", None)
        project_ids = data.pop("project_ids", None)
        permission_names_raw = data.pop("permission_names", None)

        def _payload_log() -> dict:
            out = {
                "role_name": role_name,
                "project_ids": [str(x) for x in project_ids] if project_ids is not None else None,
                "permission_names": permission_names_raw,
                "other_keys": sorted(k for k in data if k != "password"),
            }
            if "password" in data:
                out["password"] = "[omitted]"
            return out

        logger.info("update_user recebido user_id=%s payload=%s", user_id, _payload_log())

        user = await self.users.get(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

        if role_name is not None:
            rn = (role_name or "").strip()
            if not rn:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="role_name não pode ser vazio.",
                )
            if rn not in _VALID_ROLES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"role_name inválido: {rn!r}. Use ADMIN, GESTOR ou CONSULTA.",
                )
            role_name = rn

        pids: list[UUID] | None = None
        if project_ids is not None:
            pids = list(dict.fromkeys(project_ids))
            missing_proj = await ProjectRepository(self.session).missing_project_ids(pids)
            if missing_proj:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"project_ids inexistentes ou inválidos: {[str(x) for x in missing_proj]}",
                )

        perm_set: set[str] | None = None
        if permission_names_raw is not None:
            if not isinstance(permission_names_raw, list):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="permission_names deve ser uma lista de strings.",
                )
            perm_set = {str(x).strip() for x in permission_names_raw if str(x).strip()}
            perm_repo = PermissionRepository(self.session)
            missing_db = await perm_repo.missing_permission_names(perm_set)
            if missing_db:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Permissões ainda não cadastradas no banco (rode as migrations): "
                        f"{sorted(missing_db)}"
                    ),
                )

        if (project_ids is not None or permission_names_raw is not None) and role_name is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Informe role_name ao atualizar project_ids ou permission_names.",
            )

        before = model_to_dict(user)
        if "password" in data and data["password"]:
            user.password_hash = _hash_password_or_http(data.pop("password"))
        self.users.apply_updates(user, data)

        try:
            if role_name is not None or project_ids is not None:
                u_roles = await self.users.get_with_roles(user_id)
                if not u_roles:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
                rn = role_name if role_name is not None else _primary_role_name(u_roles)
                if pids is not None:
                    pids_apply = pids
                else:
                    pids_apply = await ProjectRepository(self.session).list_project_ids_for_user(user_id=user_id)
                skip_preset = perm_set is not None
                await self._apply_role_and_projects(
                    user_id=user_id,
                    role_name=rn,
                    project_ids=pids_apply,
                    apply_permission_preset=not skip_preset,
                )
            if perm_set is not None:
                try:
                    await PermissionRepository(self.session).replace_user_permissions(user_id, perm_set)
                except ValueError as e:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

            ctx: dict = {
                "descricao": "Atualização de usuário (perfil, projetos e/ou permissões)",
                "email_alvo": user.email,
            }
            if role_name is not None:
                ctx["role_name"] = role_name
            if project_ids is not None:
                ctx["project_ids"] = [str(x) for x in pids]
            if permission_names_raw is not None:
                ctx["permission_names"] = sorted(perm_set)
            await self.audit.log_action(
                user=actor,
                action="update",
                entity="user",
                entity_id=user.id,
                before=before,
                after=model_to_dict(user),
                context=ctx,
                request=request,
                force_log=bool(
                    role_name is not None or project_ids is not None or permission_names_raw is not None
                ),
            )
            await self.session.commit()
        except HTTPException:
            await self.session.rollback()
            raise
        except IntegrityError as e:
            await self.session.rollback()
            logger.exception(
                "update_user IntegrityError user_id=%s payload=%s",
                user_id,
                _payload_log(),
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dados inconsistentes (ex.: projeto ou permissão inválida). Verifique project_ids e FKs.",
            ) from e
        except Exception as e:
            await self.session.rollback()
            logger.exception(
                "update_user erro inesperado user_id=%s payload=%s err=%s",
                user_id,
                _payload_log(),
                e,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro ao atualizar usuário. Consulte os logs do servidor.",
            ) from e

        reloaded = await self.users.get_with_roles(user_id)
        if not reloaded:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
        return reloaded

    async def reset_password(
        self,
        *,
        actor_user_id,
        user_id,
        new_password: str,
        actor: User | None = None,
        request: Request | None = None,
    ) -> User:
        user = await self.users.get(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
        before = model_to_dict(user)
        before["password_hash"] = "[redacted]"
        user.password_hash = _hash_password_or_http(new_password)
        await self.session.flush()
        after = model_to_dict(user)
        after["password_hash"] = "[redacted]"
        await self.audit.log_action(
            user=actor,
            action="password_reset",
            entity="user",
            entity_id=user.id,
            before=before,
            after=after,
            context={"descricao": "Redefinição de senha pelo administrador"},
            request=request,
            force_log=True,
        )
        await self.session.commit()
        reloaded = await self.users.get_with_roles(user_id)
        if not reloaded:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
        return reloaded

    async def delete_user(
        self,
        *,
        actor_user_id,
        user_id,
        actor: User | None = None,
        request: Request | None = None,
    ) -> None:
        user = await self.users.get(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
        before = model_to_dict(user)
        await self.users.delete(user)
        await self.audit.log_action(
            user=actor,
            action="delete",
            entity="user",
            entity_id=user_id,
            before=before,
            after=None,
            context={"descricao": "Exclusão de usuário", "email": before.get("email")},
            request=request,
        )
        await self.session.commit()

    async def ensure_role(
        self,
        *,
        actor_user_id,
        name: str,
        description: str | None = None,
        actor: User | None = None,
        request: Request | None = None,
    ) -> Role:
        role = await self.roles.get_by_name(name)
        if role:
            return role
        role = Role(name=name, description=description)
        await self.roles.add(role)
        await self.audit.log_action(
            user=actor,
            action="create",
            entity="role",
            entity_id=role.id,
            before=None,
            after=model_to_dict(role),
            context={"descricao": "Criação de role", "name": name},
            request=request,
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
        actor: User | None = None,
        request: Request | None = None,
    ) -> None:
        user = await self.users.get(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
        if project_ids is not None:
            pids = list(dict.fromkeys(project_ids))
        else:
            pids = await ProjectRepository(self.session).list_project_ids_for_user(user_id=user_id)
        await self._apply_role_and_projects(
            user_id=user.id, role_name=role_name, project_ids=pids, apply_permission_preset=True
        )
        await self.audit.log_action(
            user=actor,
            action="assign_role",
            entity="user",
            entity_id=user.id,
            before=None,
            after={
                "role_name": role_name,
                "project_ids": [str(x) for x in (project_ids or [])],
            },
            context={"descricao": "Atribuição de perfil e projetos (GESTOR)"},
            request=request,
        )
        await self.session.commit()
