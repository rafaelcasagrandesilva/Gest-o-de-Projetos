from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, Request, status
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.project import Project
from app.models.project_contract import ProjectContractAdditive
from app.models.project_document import ProjectDocument, ProjectDocumentCategory
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

    async def get_project_detail(self, project_id) -> Project:
        """Projeto com os aditivos contratuais carregados (modal Detalhes)."""
        stmt = (
            select(Project)
            .where(Project.id == project_id, Project.deleted_at.is_(None))
            .options(selectinload(Project.additives))
        )
        proj = (await self.session.execute(stmt)).scalar_one_or_none()
        if proj is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado.")
        return proj

    # --- Aditivos contratuais (relação 1-N; cadastral, sem efeito financeiro) ---

    async def add_additive(self, *, project_id, data: dict) -> ProjectContractAdditive:
        await self.get_project(project_id)  # valida existência/soft-delete
        row = ProjectContractAdditive(project_id=project_id, **data)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def _get_additive(self, *, project_id, additive_id) -> ProjectContractAdditive:
        stmt = select(ProjectContractAdditive).where(
            ProjectContractAdditive.id == additive_id,
            ProjectContractAdditive.project_id == project_id,
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aditivo não encontrado.")
        return row

    async def update_additive(self, *, project_id, additive_id, data: dict) -> ProjectContractAdditive:
        row = await self._get_additive(project_id=project_id, additive_id=additive_id)
        # Campos do aditivo são todos opcionais e limpáveis: aplica inclusive None.
        for field in ("additive_date", "additive_value", "additive_duration"):
            if field in data:
                setattr(row, field, data[field])
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def delete_additive(self, *, project_id, additive_id) -> None:
        row = await self._get_additive(project_id=project_id, additive_id=additive_id)
        await self.session.delete(row)
        await self.session.commit()

    # --- Documentos do projeto (upload em disco, mesmo mecanismo dos anexos de ativos) ---

    def document_base_dir(self) -> Path:
        base = Path(settings.project_document_dir).resolve()
        base.mkdir(parents=True, exist_ok=True)
        return base

    def document_disk_path(self, row: ProjectDocument) -> Path:
        return (self.document_base_dir() / row.storage_path).resolve()

    async def _uploader_names(self, ids: set[UUID]) -> dict[UUID, str]:
        ids = {i for i in ids if i is not None}
        if not ids:
            return {}
        rows = (await self.session.execute(select(User.id, User.full_name).where(User.id.in_(ids)))).all()
        return {r.id: r.full_name for r in rows}

    async def additive_months_map(self, project_ids) -> dict[UUID, int]:
        """Σ dos prazos adicionais (meses) por projeto. Base da 'Vigência atual' (derivada)."""
        ids = list(project_ids or [])
        if not ids:
            return {}
        from app.models.project_contract import ProjectContractAdditive  # local: evita ciclo

        rows = (
            await self.session.execute(
                select(ProjectContractAdditive.project_id, ProjectContractAdditive.additive_duration).where(
                    ProjectContractAdditive.project_id.in_(ids)
                )
            )
        ).all()
        totals: dict[UUID, int] = {}
        for project_id, duration in rows:
            digits = "".join(ch for ch in str(duration or "") if ch.isdigit())
            if digits:
                totals[project_id] = totals.get(project_id, 0) + int(digits)
        return totals

    async def list_documents(self, *, project_id) -> tuple[list[ProjectDocument], dict[UUID, str]]:
        await self.get_project(project_id)  # valida existência/soft-delete
        stmt = (
            select(ProjectDocument)
            .where(ProjectDocument.project_id == project_id, ProjectDocument.is_active.is_(True))
            .order_by(ProjectDocument.uploaded_at.desc())
        )
        rows = list((await self.session.execute(stmt)).scalars().all())
        names = await self._uploader_names({r.uploaded_by for r in rows})
        return rows, names

    async def save_document(
        self,
        *,
        project_id,
        category: ProjectDocumentCategory,
        title: str,
        file_name: str,
        body: bytes,
        uploaded_by: UUID | None,
    ) -> ProjectDocument:
        await self.get_project(project_id)  # valida existência/soft-delete
        file_id = uuid4()
        ext = Path(file_name).suffix or ""
        base = self.document_base_dir() / str(project_id)
        base.mkdir(parents=True, exist_ok=True)
        dest = (base / f"{file_id}{ext}").resolve()
        dest.write_bytes(body)
        rel = str(dest.relative_to(self.document_base_dir()))
        row = ProjectDocument(
            id=file_id,
            project_id=project_id,
            category=category,
            title=title[:255],
            original_filename=file_name[:255],
            storage_path=rel,
            uploaded_by=uploaded_by,
            uploaded_at=datetime.now(timezone.utc),
            is_active=True,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def get_document(self, *, project_id, document_id) -> ProjectDocument | None:
        stmt = select(ProjectDocument).where(
            ProjectDocument.id == document_id,
            ProjectDocument.project_id == project_id,
            ProjectDocument.is_active.is_(True),
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def delete_document(self, *, project_id, document_id) -> bool:
        row = await self.get_document(project_id=project_id, document_id=document_id)
        if row is None:
            return False
        # Soft delete (preserva histórico/arquivo em disco).
        row.is_active = False
        await self.session.commit()
        return True

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

