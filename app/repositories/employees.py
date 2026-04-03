from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee, EmployeeAllocation
from app.repositories.base import Repository


class EmployeeRepository(Repository[Employee]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Employee)


class EmployeeAllocationRepository(Repository[EmployeeAllocation]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, EmployeeAllocation)

    async def list_by_project(self, *, project_id: UUID) -> list[EmployeeAllocation]:
        stmt = (
            select(EmployeeAllocation)
            .where(EmployeeAllocation.project_id == project_id)
            .order_by(EmployeeAllocation.start_date.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

