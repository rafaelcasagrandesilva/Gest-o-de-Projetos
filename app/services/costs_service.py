from __future__ import annotations

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.costs import CorporateCost, CostAllocation, ProjectFixedCost
from app.models.user import User
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

    async def create_project_fixed_cost(
        self,
        *,
        actor_user_id,
        data: dict,
        actor: User | None = None,
        request: Request | None = None,
    ) -> ProjectFixedCost:
        row = ProjectFixedCost(**data)
        await self.project_fixed.add(row)
        await self.audit.log_action(
            user=actor,
            action="create",
            entity="project_fixed_cost",
            entity_id=row.id,
            before=None,
            after=model_to_dict(row),
            context={"descricao": "Custo fixo de projeto"},
            request=request,
        )
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def create_corporate_cost(
        self,
        *,
        actor_user_id,
        data: dict,
        actor: User | None = None,
        request: Request | None = None,
    ) -> CorporateCost:
        row = CorporateCost(**data)
        await self.corporate.add(row)
        await self.audit.log_action(
            user=actor,
            action="create",
            entity="corporate_cost",
            entity_id=row.id,
            before=None,
            after=model_to_dict(row),
            context={"descricao": "Custo corporativo"},
            request=request,
        )
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def create_cost_allocation(
        self,
        *,
        actor_user_id,
        data: dict,
        actor: User | None = None,
        request: Request | None = None,
    ) -> CostAllocation:
        row = CostAllocation(**data)
        await self.allocations.add(row)
        await self.audit.log_action(
            user=actor,
            action="create",
            entity="cost_allocation",
            entity_id=row.id,
            before=None,
            after=model_to_dict(row),
            context={"descricao": "Rateio de custo"},
            request=request,
        )
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def delete_corporate_cost(
        self,
        *,
        actor_user_id,
        corporate_cost_id,
        actor: User | None = None,
        request: Request | None = None,
    ) -> None:
        row = await self.corporate.get(corporate_cost_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custo corporativo não encontrado.")
        before = model_to_dict(row)
        await self.corporate.delete(row)
        await self.audit.log_action(
            user=actor,
            action="delete",
            entity="corporate_cost",
            entity_id=corporate_cost_id,
            before=before,
            after=None,
            context={"descricao": "Exclusão de custo corporativo"},
            request=request,
        )
        await self.session.commit()

