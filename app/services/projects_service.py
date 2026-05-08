from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy import exists, select
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

    async def list_projects(self, *, offset: int = 0, limit: int = 50, status_filter: str = "ACTIVE") -> list[Project]:
        return await self.projects.list(offset=offset, limit=limit, status=status_filter, include_deleted=False)

    async def list_projects_for_user(
        self,
        *,
        user_id,
        offset: int = 0,
        limit: int = 50,
        status_filter: str = "ACTIVE",
    ) -> list[Project]:
        return await self.projects.list_for_user(
            user_id=user_id,
            offset=offset,
            limit=limit,
            status=status_filter,
            include_deleted=False,
        )

    async def get_project(self, project_id) -> Project:
        proj = await self.projects.get(project_id)
        if not proj or proj.deleted_at is not None:
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
        if await self._has_financial_data(project_id=proj.id):
            raise HTTPException(
                status_code=409,
                detail="Projeto possui dados vinculados e não pode ser excluído",
            )

        before = model_to_dict(proj)
        now = datetime.now(timezone.utc)
        proj.deleted_at = now
        proj.is_active = False
        if proj.closed_at is None:
            proj.closed_at = now
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

    async def deactivate_project(
        self,
        *,
        project_id,
        actor: User | None = None,
        request: Request | None = None,
    ) -> Project:
        proj = await self.get_project(project_id)
        # DEBUG temporário (remover após validação em produção)
        print("Encerrando projeto:", proj.id, flush=True)
        if not proj.is_active:
            return proj
        before = model_to_dict(proj)
        now = datetime.now(timezone.utc)
        proj.is_active = False
        proj.closed_at = now
        await self.audit.log_action(
            user=actor,
            action="deactivate",
            entity="project",
            entity_id=project_id,
            before=before,
            after=model_to_dict(proj),
            context={"project_name": proj.name, "descricao": "Encerramento de projeto"},
            request=request,
        )
        await self.session.commit()
        await self.session.refresh(proj)
        return proj

    async def activate_project(
        self,
        *,
        project_id,
        actor: User | None = None,
        request: Request | None = None,
    ) -> Project:
        proj = await self.get_project(project_id)
        if proj.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Projeto não encontrado.")
        if proj.is_active and proj.closed_at is None:
            return proj
        before = model_to_dict(proj)
        proj.is_active = True
        proj.closed_at = None
        await self.audit.log_action(
            user=actor,
            action="activate",
            entity="project",
            entity_id=project_id,
            before=before,
            after=model_to_dict(proj),
            context={"project_name": proj.name, "descricao": "Reativação de projeto"},
            request=request,
        )
        await self.session.commit()
        await self.session.refresh(proj)
        return proj

    async def _has_financial_data(self, *, project_id) -> bool:
        """
        Bloqueio de soft delete quando o projeto possui vínculos financeiros/custos.
        Mantém histórico: se houver dados, apenas encerrar é permitido.
        """
        # Import local para evitar ciclos.
        from app.models.costs import CostAllocation, ProjectCost, ProjectFixedCost  # noqa: WPS433
        from app.models.employee import EmployeeAllocation  # noqa: WPS433
        from app.models.financial import Invoice, Revenue  # noqa: WPS433
        from app.models.receivable import ReceivableInvoice  # noqa: WPS433

        checks = [
            exists(select(Revenue.id).where(Revenue.project_id == project_id)),
            exists(select(Invoice.id).where(Invoice.project_id == project_id)),
            exists(select(ReceivableInvoice.id).where(ReceivableInvoice.project_id == project_id)),
            exists(select(ProjectCost.id).where(ProjectCost.project_id == project_id)),
            exists(select(ProjectFixedCost.id).where(ProjectFixedCost.project_id == project_id)),
            exists(select(CostAllocation.id).where(CostAllocation.project_id == project_id)),
            exists(select(EmployeeAllocation.id).where(EmployeeAllocation.project_id == project_id)),
        ]
        for cond in checks:
            res = await self.session.execute(select(cond))
            if bool(res.scalar()):
                return True
        return False

