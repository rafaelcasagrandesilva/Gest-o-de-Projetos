from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.costs import CorporateCost, CostAllocation, ProjectFixedCost
from app.repositories.base import Repository


class ProjectFixedCostRepository(Repository[ProjectFixedCost]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ProjectFixedCost)


class CorporateCostRepository(Repository[CorporateCost]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, CorporateCost)


class CostAllocationRepository(Repository[CostAllocation]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, CostAllocation)

