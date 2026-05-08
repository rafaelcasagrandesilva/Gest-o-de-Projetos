from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.permission import UserPermission
from app.models.user import Role, User, UserRole
from app.repositories.base import Repository


class UserRepository(Repository[User]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, User)

    async def list(self, *, offset: int = 0, limit: int = 50, include_deleted: bool = False) -> list[User]:
        stmt = select(User).options(
            selectinload(User.roles).selectinload(UserRole.role),
            selectinload(User.user_permissions).selectinload(UserPermission.permission),
        )
        if not include_deleted:
            stmt = stmt.where(User.deleted_at.is_(None))
        stmt = stmt.offset(offset).limit(limit)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_with_roles(self, user_id: UUID) -> User | None:
        stmt = (
            select(User)
            .options(
                selectinload(User.roles).selectinload(UserRole.role),
                selectinload(User.user_permissions).selectinload(UserPermission.permission),
            )
            .where(User.id == user_id)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_email(self, email: str, *, include_deleted: bool = False) -> User | None:
        stmt = select(User).where(User.email == email)
        if not include_deleted:
            stmt = stmt.where(User.deleted_at.is_(None))
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def count_active_admins(self) -> int:
        stmt = (
            select(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                Role.name == "ADMIN",
                User.deleted_at.is_(None),
                User.is_active.is_(True),
            )
        )
        res = await self.session.execute(stmt)
        return len(list(res.scalars().all()))


class RoleRepository(Repository[Role]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Role)

    async def get_by_name(self, name: str) -> Role | None:
        stmt = select(Role).where(Role.name == name)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

