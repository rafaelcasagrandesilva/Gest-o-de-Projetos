from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.user import ProjectUser
from app.repositories.base import Repository


class ProjectRepository(Repository[Project]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Project)

    async def list_all_project_ids(self) -> list[UUID]:
        stmt = select(Project.id)
        res = await self.session.execute(stmt)
        return [row[0] for row in res.all()]

    async def list_project_ids_for_user(self, *, user_id: UUID) -> list[UUID]:
        stmt = select(ProjectUser.project_id).where(ProjectUser.user_id == user_id)
        res = await self.session.execute(stmt)
        return [row[0] for row in res.all()]

    async def list_for_user(self, *, user_id: UUID, offset: int = 0, limit: int = 50) -> list[Project]:
        stmt = (
            select(Project)
            .join(ProjectUser, ProjectUser.project_id == Project.id)
            .where(ProjectUser.user_id == user_id)
            .offset(offset)
            .limit(limit)
        )
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

