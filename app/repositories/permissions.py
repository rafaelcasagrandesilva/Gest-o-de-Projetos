from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.permission import Permission, RolePermission, UserPermission
from app.repositories.base import Repository

logger = logging.getLogger(__name__)


class PermissionRepository(Repository[Permission]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Permission)

    async def missing_permission_names(self, names: set[str]) -> set[str]:
        """Nomes que não existem na tabela `permissions`."""
        if not names:
            return set()
        stmt = select(Permission.name).where(Permission.name.in_(names))
        res = await self.session.execute(stmt)
        found = {row[0] for row in res.all()}
        return names - found

    async def ensure_permission_names(self, names: set[str]) -> None:
        """Insere permissões conhecidas que ainda não existem; operação idempotente."""
        missing = await self.missing_permission_names(names)
        for name in sorted(missing):
            self.session.add(Permission(name=name))
        if missing:
            await self.session.flush()

    async def replace_user_permissions(self, user_id: UUID, names: set[str]) -> None:
        """DELETE vínculos antigos; INSERT novos (sem duplicar permission_id)."""
        try:
            await self.session.execute(delete(UserPermission).where(UserPermission.user_id == user_id))
            await self.session.flush()
            if not names:
                return
            # Uma entrada por nome; ordem estável para inserts previsíveis
            unique_names = list(dict.fromkeys(names))
            stmt = select(Permission).where(Permission.name.in_(unique_names))
            res = await self.session.execute(stmt)
            perms = list(res.scalars().all())
            by_name = {p.name: p for p in perms}
            missing = [n for n in unique_names if n not in by_name]
            if missing:
                raise ValueError(f"Permissões desconhecidas no banco: {sorted(missing)}")
            seen_ids: set[UUID] = set()
            for n in unique_names:
                p = by_name[n]
                if p.id in seen_ids:
                    continue
                seen_ids.add(p.id)
                self.session.add(UserPermission(user_id=user_id, permission_id=p.id))
        except ProgrammingError as e:
            detail = str(e.orig) if getattr(e, "orig", None) else str(e)
            if "does not exist" in detail:
                logger.warning(
                    "Tabelas RBAC ausentes; replace_user_permissions ignorado. Rode alembic upgrade head."
                )
                return
            raise

    # --- Perfis (role_permissions) e deltas do usuário -----------------------------------
    async def role_permission_names(self, role_id: UUID) -> set[str]:
        stmt = (
            select(Permission.name)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
        )
        res = await self.session.execute(stmt)
        return {row[0] for row in res.all()}

    async def replace_role_permissions(self, role_id: UUID, names: set[str]) -> None:
        """DELETE vínculos do perfil; INSERT novos (valida nomes contra a tabela permissions)."""
        await self.ensure_permission_names(names)
        await self.session.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
        await self.session.flush()
        if not names:
            return
        unique_names = list(dict.fromkeys(names))
        res = await self.session.execute(select(Permission).where(Permission.name.in_(unique_names)))
        by_name = {p.name: p for p in res.scalars().all()}
        missing = [n for n in unique_names if n not in by_name]
        if missing:
            raise ValueError(f"Permissões desconhecidas no banco: {sorted(missing)}")
        seen: set[UUID] = set()
        for n in unique_names:
            p = by_name[n]
            if p.id in seen:
                continue
            seen.add(p.id)
            self.session.add(RolePermission(role_id=role_id, permission_id=p.id))

    async def set_user_permission_deltas(self, user_id: UUID, full_set: set[str], role_perms: set[str]) -> None:
        """Grava o conjunto EFETIVO desejado (`full_set`) como DELTAS relativos ao(s) perfil(is):
        adições (full − role, granted=true) e remoções (role − full, granted=false). Permissões em
        (full ∩ role) não geram linha (seguem o perfil — vínculo vivo).
        """
        adds = set(full_set) - set(role_perms)
        removes = set(role_perms) - set(full_set)
        await self.ensure_permission_names(adds | removes)
        await self.session.execute(delete(UserPermission).where(UserPermission.user_id == user_id))
        await self.session.flush()
        if not (adds or removes):
            return
        res = await self.session.execute(
            select(Permission).where(Permission.name.in_(list(adds | removes)))
        )
        by_name = {p.name: p for p in res.scalars().all()}
        for n in sorted(adds):
            p = by_name.get(n)
            if p is not None:
                self.session.add(UserPermission(user_id=user_id, permission_id=p.id, granted=True))
        for n in sorted(removes):
            p = by_name.get(n)
            if p is not None:
                self.session.add(UserPermission(user_id=user_id, permission_id=p.id, granted=False))
