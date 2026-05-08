from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.user import ProjectUser
from app.repositories.base import Repository


class ProjectRepository(Repository[Project]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Project)

    def _base_stmt(self, *, include_deleted: bool, status: str) -> Select:
        stmt = select(Project)
        if not include_deleted:
            stmt = stmt.where(Project.deleted_at.is_(None))
        if status == "ACTIVE":
            stmt = stmt.where(and_(Project.is_active.is_(True), Project.closed_at.is_(None)))
        elif status == "CLOSED":
            stmt = stmt.where(Project.is_active.is_(False))
        return stmt.order_by(Project.name.asc())

    async def list_all_project_ids(self) -> list[UUID]:
        stmt = select(Project.id).where(Project.deleted_at.is_(None))
        res = await self.session.execute(stmt)
        return [row[0] for row in res.all()]

    async def list_project_ids_for_user(self, *, user_id: UUID) -> list[UUID]:
        stmt = select(ProjectUser.project_id).where(ProjectUser.user_id == user_id)
        res = await self.session.execute(stmt)
        return [row[0] for row in res.all()]

    async def list_for_user(
        self,
        *,
        user_id: UUID,
        offset: int = 0,
        limit: int = 50,
        status: str = "ACTIVE",
        include_deleted: bool = False,
    ) -> list[Project]:
        stmt = (
            self._base_stmt(include_deleted=include_deleted, status=status)
            .join(ProjectUser, ProjectUser.project_id == Project.id)
            .where(ProjectUser.user_id == user_id)
            .offset(offset)
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        status: str = "ACTIVE",
        include_deleted: bool = False,
    ) -> list[Project]:
        stmt = self._base_stmt(include_deleted=include_deleted, status=status).offset(offset).limit(limit)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def user_has_access(self, *, user_id: UUID, project_id: UUID) -> bool:
        stmt = select(ProjectUser.id).where(ProjectUser.user_id == user_id, ProjectUser.project_id == project_id)
        res = await self.session.execute(stmt)
        return res.first() is not None

    async def missing_project_ids(self, ids: list[UUID]) -> list[UUID]:
        """IDs que não existem na tabela `projects` (ordem preservada, sem duplicar)."""
        if not ids:
            return []
        uniq = list(dict.fromkeys(ids))
        stmt = select(Project.id).where(Project.id.in_(uniq))
        res = await self.session.execute(stmt)
        found = {row[0] for row in res.all()}
        return [pid for pid in uniq if pid not in found]

