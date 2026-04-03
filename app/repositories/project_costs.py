from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.costs import ProjectCost
from app.repositories.base import Repository


class ProjectCostRepository(Repository[ProjectCost]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ProjectCost)

    async def list_by_project(self, *, project_id: UUID, offset: int = 0, limit: int = 200) -> list[ProjectCost]:
        stmt = (
            select(ProjectCost)
            .where(ProjectCost.project_id == project_id)
            .order_by(ProjectCost.cost_date.desc())
            .offset(offset)
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())
