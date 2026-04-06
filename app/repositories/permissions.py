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
        try:
            await self.session.execute(delete(UserPermission).where(UserPermission.user_id == user_id))
            if not names:
                return
            stmt = select(Permission).where(Permission.name.in_(names))
            res = await self.session.execute(stmt)
            perms = list(res.scalars().all())
            found = {p.name for p in perms}
            missing = names - found
            if missing:
                raise ValueError(f"Permissões desconhecidas: {sorted(missing)}")
            for p in perms:
                self.session.add(UserPermission(user_id=user_id, permission_id=p.id))
        except ProgrammingError as e:
            detail = str(e.orig) if getattr(e, "orig", None) else str(e)
            if "does not exist" in detail:
                logger.warning(
                    "Tabelas RBAC ausentes; replace_user_permissions ignorado. Rode alembic upgrade head."
                )
                return
            raise
