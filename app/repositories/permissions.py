from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.permission import Permission, UserPermission
from app.repositories.base import Repository


class PermissionRepository(Repository[Permission]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Permission)

    async def replace_user_permissions(self, user_id: UUID, names: set[str]) -> None:
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
