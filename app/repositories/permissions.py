from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.permission import Permission, UserPermission
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
