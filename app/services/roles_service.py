"""Gestão de Perfis (Roles) administráveis.

O perfil é apenas um AGRUPADOR de Permission existentes (role_permissions). Toda a autorização
continua baseada nas mesmas Permission e no mesmo `require_permission` — este serviço só
administra o agrupamento. Regras: perfis de sistema (ADMIN/GESTOR/CONSULTA) não podem ser
renomeados nem desativados; ADMIN é totalmente protegido (permissões somente leitura); perfis
inativos não são ofertáveis a novos vínculos; exclusão permitida para QUALQUER perfil (inclusive
de sistema) desde que não tenha usuários vinculados.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ROLE_ADMIN
from app.models.permission import RolePermission
from app.models.user import Role, User, UserRole
from app.repositories.permissions import PermissionRepository
from app.services.audit_service import AuditService
from app.services.utils import model_to_dict

SYSTEM_ROLE_NAMES = frozenset({"ADMIN", "GESTOR", "CONSULTA"})
_SYSTEM_ORDER = {"ADMIN": 0, "GESTOR": 1, "CONSULTA": 2}


class RolesService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.perms = PermissionRepository(session)
        self.audit = AuditService(session)

    async def _get(self, role_id: UUID) -> Role:
        role = (await self.session.execute(select(Role).where(Role.id == role_id))).scalar_one_or_none()
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Perfil não encontrado.")
        return role

    async def _user_counts(self) -> dict[UUID, int]:
        rows = await self.session.execute(
            select(UserRole.role_id, func.count(UserRole.user_id)).group_by(UserRole.role_id)
        )
        return {rid: n for rid, n in rows.all()}

    async def _to_read(self, role: Role, counts: dict[UUID, int] | None = None) -> dict:
        if counts is None:
            counts = await self._user_counts()
        return {
            **model_to_dict(role),
            "is_system": role.is_system,
            "is_active": role.is_active,
            "user_count": counts.get(role.id, 0),
            "permission_names": sorted(await self.perms.role_permission_names(role.id)),
        }

    async def list_roles(self) -> list[dict]:
        roles = list((await self.session.execute(select(Role))).scalars().all())
        counts = await self._user_counts()
        # Sistema no topo (ordem canônica), demais alfabético.
        roles.sort(key=lambda r: (0, _SYSTEM_ORDER.get(r.name, 99)) if r.is_system else (1, r.name.lower()))
        return [await self._to_read(r, counts) for r in roles]

    async def create_role(
        self,
        *,
        name: str,
        description: str | None,
        is_active: bool,
        permission_names: list[str] | None,
        base_role_id: UUID | None,
        actor: User | None,
        request: Request | None,
    ) -> dict:
        name = (name or "").strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Informe o nome do perfil.")
        if (await self.session.execute(select(Role).where(func.lower(Role.name) == name.lower()))).scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Já existe um perfil {name!r}.")
        # Permissões: explícitas ou copiadas do perfil base (duplicação).
        if permission_names is None and base_role_id is not None:
            base = await self._get(base_role_id)
            perm_set = await self.perms.role_permission_names(base.id)
        else:
            perm_set = {str(p).strip() for p in (permission_names or []) if str(p).strip()}

        role = Role(name=name, description=(description or None), is_system=False, is_active=is_active)
        self.session.add(role)
        await self.session.flush()
        await self.perms.replace_role_permissions(role.id, perm_set)
        await self.audit.log_action(
            user=actor, action="create", entity="role", entity_id=role.id,
            before=None, after={"name": name, "permission_names": sorted(perm_set), "is_active": is_active},
            context={"descricao": "Criação de perfil", "name": name, "base_role_id": str(base_role_id) if base_role_id else None},
            request=request, force_log=True,
        )
        await self.session.commit()
        return await self._to_read(await self._get(role.id))

    async def update_role(
        self, *, role_id: UUID, data: dict, actor: User | None, request: Request | None
    ) -> dict:
        role = await self._get(role_id)
        before = {**model_to_dict(role), "permission_names": sorted(await self.perms.role_permission_names(role.id))}
        is_admin = role.name == ROLE_ADMIN

        new_name = data.get("name")
        new_desc = data.get("description")
        new_active = data.get("is_active")
        new_perms = data.get("permission_names")

        if new_name is not None and new_name.strip() and new_name.strip() != role.name:
            if role.is_system:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Perfis de sistema não podem ser renomeados.")
            if (await self.session.execute(
                select(Role).where(func.lower(Role.name) == new_name.strip().lower(), Role.id != role.id)
            )).scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Já existe um perfil {new_name!r}.")
            role.name = new_name.strip()
        if new_desc is not None:
            role.description = new_desc or None
        if new_active is not None:
            if role.is_system and not new_active:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Perfis de sistema não podem ser desativados.")
            role.is_active = bool(new_active)

        perms_changed = False
        if new_perms is not None:
            if is_admin:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="As permissões do perfil ADMIN não podem ser alteradas (acesso irrestrito do sistema).",
                )
            perm_set = {str(p).strip() for p in new_perms if str(p).strip()}
            try:
                await self.perms.replace_role_permissions(role.id, perm_set)
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
            perms_changed = True

        # Ação única e curta (coluna audit_logs.action é limitada); detalhes vão no contexto.
        if new_active is not None:
            action = "activate" if new_active else "deactivate"
        elif perms_changed:
            action = "role_perms"
        else:
            action = "update"

        await self.session.flush()
        after = {**model_to_dict(role), "permission_names": sorted(await self.perms.role_permission_names(role.id))}
        await self.audit.log_action(
            user=actor, action=action, entity="role", entity_id=role.id,
            before=before, after=after,
            context={"descricao": "Edição de perfil", "name": role.name, "perms_changed": perms_changed},
            request=request, force_log=True,
        )
        await self.session.commit()
        return await self._to_read(await self._get(role.id))

    async def delete_role(self, *, role_id: UUID, actor: User | None, request: Request | None) -> None:
        role = await self._get(role_id)
        # Regra única de exclusão: qualquer perfil (inclusive de sistema — ADMIN/GESTOR/CONSULTA)
        # pode ser excluído DESDE QUE não tenha usuários vinculados. A contagem de vínculos é a
        # única trava. Observação operacional: se a role ADMIN ficar sem usuários e for excluída,
        # o seed de startup (bootstrap.seed_admin) a recria junto de um admin padrão.
        n_users = (await self.session.execute(
            select(func.count(UserRole.user_id)).where(UserRole.role_id == role.id)
        )).scalar_one()
        if n_users:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"O perfil possui {n_users} usuário(s) vinculado(s); realoque-os antes de excluir.",
            )
        before = {**model_to_dict(role), "permission_names": sorted(await self.perms.role_permission_names(role.id))}
        await self.session.delete(role)  # cascata remove role_permissions
        await self.audit.log_action(
            user=actor, action="delete", entity="role", entity_id=role.id,
            before=before, after=None, context={"descricao": "Exclusão de perfil", "name": role.name},
            request=request, force_log=True,
        )
        await self.session.commit()
