from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.costs import CorporateCost, CostAllocation, ProjectFixedCost
from app.repositories.costs import CorporateCostRepository, CostAllocationRepository, ProjectFixedCostRepository
from app.services.audit_service import AuditService
from app.services.utils import model_to_dict


class CostsService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.project_fixed = ProjectFixedCostRepository(session)
        self.corporate = CorporateCostRepository(session)
        self.allocations = CostAllocationRepository(session)
        self.audit = AuditService(session)

    async def create_project_fixed_cost(self, *, actor_user_id, data: dict) -> ProjectFixedCost:
        row = ProjectFixedCost(**data)
        await self.project_fixed.add(row)
        await self.audit.log(
            actor_user_id=actor_user_id,
            action="create",
            entity="ProjectFixedCost",
            entity_id=row.id,
            before=None,
            after=model_to_dict(row),
        )
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def create_corporate_cost(self, *, actor_user_id, data: dict) -> CorporateCost:
        row = CorporateCost(**data)
        await self.corporate.add(row)
        await self.audit.log(
            actor_user_id=actor_user_id,
            action="create",
            entity="CorporateCost",
            entity_id=row.id,
            before=None,
            after=model_to_dict(row),
        )
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def create_cost_allocation(self, *, actor_user_id, data: dict) -> CostAllocation:
        row = CostAllocation(**data)
        await self.allocations.add(row)
        await self.audit.log(
            actor_user_id=actor_user_id,
            action="create",
            entity="CostAllocation",
            entity_id=row.id,
            before=None,
            after=model_to_dict(row),
        )
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def delete_corporate_cost(self, *, actor_user_id, corporate_cost_id) -> None:
        row = await self.corporate.get(corporate_cost_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custo corporativo não encontrado.")
        before = model_to_dict(row)
        await self.corporate.delete(row)
        await self.audit.log(
            actor_user_id=actor_user_id,
            action="delete",
            entity="CorporateCost",
            entity_id=corporate_cost_id,
            before=before,
            after=None,
        )
        await self.session.commit()

