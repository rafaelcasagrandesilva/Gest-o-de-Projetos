from __future__ import annotations

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.user import User
from app.repositories.projects import ProjectRepository
from app.services.audit_service import AuditService
from app.services.utils import model_to_dict


class ProjectsService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.projects = ProjectRepository(session)
        self.audit = AuditService(session)

    async def list_projects(self, *, offset: int = 0, limit: int = 50) -> list[Project]:
        return await self.projects.list(offset=offset, limit=limit)

    async def list_projects_for_user(self, *, user_id, offset: int = 0, limit: int = 50) -> list[Project]:
        return await self.projects.list_for_user(user_id=user_id, offset=offset, limit=limit)

    async def get_project(self, project_id) -> Project:
        proj = await self.projects.get(project_id)
        if not proj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado.")
        return proj

    async def create_project(
        self,
        *,
        actor_user_id,
        data: dict,
        actor: User | None = None,
        request: Request | None = None,
    ) -> Project:
        proj = Project(**data)
        await self.projects.add(proj)
        await self.audit.log_action(
            user=actor,
            action="create",
            entity="project",
            entity_id=proj.id,
            before=None,
            after=model_to_dict(proj),
            context={"project_name": proj.name, "descricao": "Cadastro de projeto"},
            request=request,
        )
        await self.session.commit()
        await self.session.refresh(proj)
        return proj

    async def update_project(
        self,
        *,
        actor_user_id,
        project_id,
        data: dict,
        actor: User | None = None,
        request: Request | None = None,
    ) -> Project:
        proj = await self.get_project(project_id)
        before = model_to_dict(proj)
        self.projects.apply_updates(proj, data)
        await self.audit.log_action(
            user=actor,
            action="update",
            entity="project",
            entity_id=proj.id,
            before=before,
            after=model_to_dict(proj),
            context={"project_name": proj.name, "descricao": "Atualização de projeto"},
            request=request,
        )
        await self.session.commit()
        await self.session.refresh(proj)
        return proj

    async def delete_project(
        self,
        *,
        actor_user_id,
        project_id,
        actor: User | None = None,
        request: Request | None = None,
    ) -> None:
        proj = await self.get_project(project_id)
        before = model_to_dict(proj)
        await self.projects.delete(proj)
        await self.audit.log_action(
            user=actor,
            action="delete",
            entity="project",
            entity_id=project_id,
            before=before,
            after=None,
            context={
                "project_name": before.get("name"),
                "descricao": "Exclusão de projeto",
            },
            request=request,
        )
        await self.session.commit()

