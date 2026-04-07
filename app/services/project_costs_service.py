from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.costs import ProjectCost
from app.models.user import User
from app.repositories.project_costs import ProjectCostRepository
from app.services.audit_service import AuditService
from app.services.utils import model_to_dict


class ProjectCostsService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ProjectCostRepository(session)
        self.audit = AuditService(session)

    async def list_by_project(self, *, project_id: UUID, offset: int = 0, limit: int = 200) -> list[ProjectCost]:
        return await self.repo.list_by_project(project_id=project_id, offset=offset, limit=limit)

    async def create(
        self,
        *,
        actor_user_id,
        data: dict,
        actor: User | None = None,
        request: Request | None = None,
    ) -> ProjectCost:
        row = ProjectCost(**data)
        await self.repo.add(row)
        await self.audit.log_action(
            user=actor,
            action="create",
            entity="project_cost",
            entity_id=row.id,
            before=None,
            after=model_to_dict(row),
            context={"descricao": "Custo de projeto (billing)"},
            request=request,
        )
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def update(
        self,
        *,
        actor_user_id,
        cost_id: UUID,
        data: dict,
        actor: User | None = None,
        request: Request | None = None,
    ) -> ProjectCost:
        row = await self.repo.get(cost_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custo não encontrado.")
        before = model_to_dict(row)
        self.repo.apply_updates(row, {k: v for k, v in data.items() if v is not None})
        await self.audit.log_action(
            user=actor,
            action="update",
            entity="project_cost",
            entity_id=row.id,
            before=before,
            after=model_to_dict(row),
            context={"descricao": "Atualização de custo de projeto"},
            request=request,
        )
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def delete(
        self,
        *,
        actor_user_id,
        cost_id: UUID,
        actor: User | None = None,
        request: Request | None = None,
    ) -> None:
        row = await self.repo.get(cost_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custo não encontrado.")
        before = model_to_dict(row)
        await self.repo.delete(row)
        await self.audit.log_action(
            user=actor,
            action="delete",
            entity="project_cost",
            entity_id=cost_id,
            before=before,
            after=None,
            context={"descricao": "Exclusão de custo de projeto"},
            request=request,
        )
        await self.session.commit()
