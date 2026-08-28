from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    require_permission,
    require_project_access,
    user_sees_all_projects,
)
from app.core.config import settings
from app.core.permission_codes import (
    PROJECTS_CREATE,
    PROJECTS_DELETE,
    PROJECTS_DOCUMENTS_DELETE,
    PROJECTS_DOCUMENTS_UPLOAD,
    PROJECTS_DOCUMENTS_VIEW,
    PROJECTS_LIST,
    PROJECTS_READ,
    PROJECTS_UPDATE,
    USERS_MANAGE,
)
from app.models.project_document import ProjectDocument, ProjectDocumentCategory
from app.api.sensitive import redact_for
from app.database.session import get_db
from app.models.user import ProjectUser, User
from app.schemas.projects import (
    ProjectContractAdditiveCreate,
    ProjectContractAdditiveRead,
    ProjectContractAdditiveUpdate,
    ProjectCreate,
    ProjectDetailRead,
    ProjectDocumentRead,
    ProjectRead,
    ProjectUpdate,
)
from app.services.projects_service import ProjectsService


router = APIRouter()


@router.get("/", response_model=list[ProjectRead], dependencies=[Depends(require_permission(PROJECTS_LIST))])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status_filter: str = Query(default="ACTIVE", alias="status", pattern="^(ACTIVE|CLOSED|ALL)$"),
) -> list[ProjectRead]:
    svc = ProjectsService(db)
    if user_sees_all_projects(user):
        rows = await svc.list_projects(offset=offset, limit=limit, status_filter=status_filter)
    else:
        rows = await svc.list_projects_for_user(user_id=user.id, offset=offset, limit=limit, status_filter=status_filter)
    months = await svc.additive_months_map([p.id for p in rows])
    out: list[ProjectRead] = []
    for p in rows:
        r = ProjectRead.model_validate(p)
        r.additive_months_total = months.get(p.id, 0)
        out.append(r)
    return [redact_for("project", _m, user) for _m in out]


# Os endpoints `/{project_id}/allocations` (GET/POST) do vínculo percentual legado
# (`EmployeeAllocation`) foram REMOVIDOS na limpeza da RC: 0 linhas na tabela, nenhum consumidor
# no frontend. Quem faz colaborador × projeto hoje é `ProjectLabor` (aba Mão de Obra) e, na camada
# contratual, `EmployeeAssignment` (`/employees/{id}/assignments`). A tabela permanece no banco.


@router.get("/{project_id}", response_model=ProjectDetailRead, dependencies=[Depends(require_permission(PROJECTS_READ))])
async def get_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access),
) -> ProjectDetailRead:
    proj = await ProjectsService(db).get_project_detail(project_id)
    read = ProjectDetailRead.model_validate(proj)
    # Vigência atual = início + prazo + Σ prazos dos aditivos já carregados.
    read.additive_months_total = sum(
        int("".join(ch for ch in str(a.additive_duration or "") if ch.isdigit()) or 0) for a in proj.additives
    )
    return redact_for("project", read, user)


@router.get(
    "/{project_id}/additives",
    response_model=list[ProjectContractAdditiveRead],
    dependencies=[Depends(require_permission(PROJECTS_READ))],
)
async def list_project_additives(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access),
) -> list[ProjectContractAdditiveRead]:
    proj = await ProjectsService(db).get_project_detail(project_id)
    return [redact_for("project", ProjectContractAdditiveRead.model_validate(a), user) for a in proj.additives]


@router.post(
    "/{project_id}/additives",
    response_model=ProjectContractAdditiveRead,
    status_code=201,
    dependencies=[Depends(require_permission(PROJECTS_UPDATE))],
)
async def create_project_additive(
    project_id: UUID,
    payload: ProjectContractAdditiveCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access),
) -> ProjectContractAdditiveRead:
    row = await ProjectsService(db).add_additive(project_id=project_id, data=payload.model_dump())
    return redact_for("project", ProjectContractAdditiveRead.model_validate(row), user)


@router.patch(
    "/{project_id}/additives/{additive_id}",
    response_model=ProjectContractAdditiveRead,
    dependencies=[Depends(require_permission(PROJECTS_UPDATE))],
)
async def update_project_additive(
    project_id: UUID,
    additive_id: UUID,
    payload: ProjectContractAdditiveUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access),
) -> ProjectContractAdditiveRead:
    row = await ProjectsService(db).update_additive(
        project_id=project_id, additive_id=additive_id, data=payload.model_dump(exclude_unset=True)
    )
    return redact_for("project", ProjectContractAdditiveRead.model_validate(row), user)


@router.delete(
    "/{project_id}/additives/{additive_id}",
    status_code=204,
    dependencies=[Depends(require_permission(PROJECTS_UPDATE))],
)
async def delete_project_additive(
    project_id: UUID,
    additive_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_project_access),
) -> None:
    await ProjectsService(db).delete_additive(project_id=project_id, additive_id=additive_id)


def _document_to_read(doc: ProjectDocument, uploader_name: str | None) -> ProjectDocumentRead:
    return ProjectDocumentRead(
        id=doc.id,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        project_id=doc.project_id,
        category=doc.category.value,  # type: ignore[arg-type]
        title=doc.title,
        original_filename=doc.original_filename,
        uploaded_by=doc.uploaded_by,
        uploaded_by_name=uploader_name,
        uploaded_at=doc.uploaded_at,
        download_url=f"projects/{doc.project_id}/documents/{doc.id}/download",
    )


@router.get(
    "/{project_id}/documents",
    response_model=list[ProjectDocumentRead],
    dependencies=[Depends(require_permission(PROJECTS_DOCUMENTS_VIEW))],
)
async def list_project_documents(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_project_access),
) -> list[ProjectDocumentRead]:
    rows, names = await ProjectsService(db).list_documents(project_id=project_id)
    return [_document_to_read(d, names.get(d.uploaded_by) if d.uploaded_by else None) for d in rows]


@router.post(
    "/{project_id}/documents",
    response_model=ProjectDocumentRead,
    status_code=201,
    dependencies=[Depends(require_permission(PROJECTS_DOCUMENTS_UPLOAD))],
)
async def upload_project_document(
    project_id: UUID,
    file: UploadFile = File(...),
    category: ProjectDocumentCategory = Form(default=ProjectDocumentCategory.OUTRO),
    title: str = Form(...),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
    _: User = Depends(require_project_access),
) -> ProjectDocumentRead:
    clean_title = (title or "").strip()
    if not clean_title:
        raise HTTPException(status_code=400, detail="Informe o título do documento.")
    body = await file.read()
    if len(body) > settings.project_document_max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo excede o limite de {settings.project_document_max_bytes // (1024 * 1024)} MB.",
        )
    try:
        doc = await ProjectsService(db).save_document(
            project_id=project_id,
            category=category,
            title=clean_title,
            file_name=(file.filename or "arquivo").strip(),
            body=body,
            uploaded_by=actor.id,
        )
    except HTTPException:
        raise
    return _document_to_read(doc, actor.full_name)


@router.get(
    "/{project_id}/documents/{document_id}/download",
    dependencies=[Depends(require_permission(PROJECTS_DOCUMENTS_VIEW))],
)
async def download_project_document(
    project_id: UUID,
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_project_access),
) -> FileResponse:
    svc = ProjectsService(db)
    doc = await svc.get_document(project_id=project_id, document_id=document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    path = svc.document_disk_path(doc)
    if not path.is_file():
        # O registro existe no banco, mas o binário sumiu do disco (ex.: redeploy
        # sem volume persistente). Mensagem explícita para não parecer erro de rede.
        raise HTTPException(
            status_code=404,
            detail="Arquivo não encontrado no armazenamento do servidor. Reenvie o documento.",
        )
    return FileResponse(path, filename=doc.original_filename)


@router.delete(
    "/{project_id}/documents/{document_id}",
    status_code=204,
    dependencies=[Depends(require_permission(PROJECTS_DOCUMENTS_DELETE))],
)
async def delete_project_document(
    project_id: UUID,
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_project_access),
) -> None:
    ok = await ProjectsService(db).delete_document(project_id=project_id, document_id=document_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")


@router.post("/", response_model=ProjectRead, dependencies=[Depends(require_permission(PROJECTS_CREATE))])
async def create_project(
    payload: ProjectCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> ProjectRead:
    proj = await ProjectsService(db).create_project(
        actor_user_id=actor.id, data=payload.model_dump(), actor=actor, request=request
    )
    return redact_for("project", ProjectRead.model_validate(proj), actor)


@router.patch("/{project_id}", response_model=ProjectRead, dependencies=[Depends(require_permission(PROJECTS_UPDATE))])
async def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
    _: User = Depends(require_project_access),
) -> ProjectRead:
    proj = await ProjectsService(db).update_project(
        actor_user_id=actor.id,
        project_id=project_id,
        data=payload.model_dump(),
        actor=actor,
        request=request,
    )
    return redact_for("project", ProjectRead.model_validate(proj), actor)


@router.delete("/{project_id}", status_code=204, dependencies=[Depends(require_permission(PROJECTS_DELETE))])
async def delete_project(
    project_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
    _: User = Depends(require_project_access),
) -> None:
    await ProjectsService(db).delete_project(
        actor_user_id=actor.id, project_id=project_id, actor=actor, request=request
    )


@router.patch("/{project_id}/deactivate", response_model=ProjectRead, dependencies=[Depends(require_permission(PROJECTS_UPDATE))])
async def deactivate_project(
    project_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
    _: User = Depends(require_project_access),
) -> ProjectRead:
    proj = await ProjectsService(db).deactivate_project(project_id=project_id, actor=actor, request=request)
    return redact_for("project", ProjectRead.model_validate(proj), actor)


@router.patch("/{project_id}/activate", response_model=ProjectRead, dependencies=[Depends(require_permission(PROJECTS_UPDATE))])
async def activate_project(
    project_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
    _: User = Depends(require_project_access),
) -> ProjectRead:
    proj = await ProjectsService(db).activate_project(project_id=project_id, actor=actor, request=request)
    return redact_for("project", ProjectRead.model_validate(proj), actor)


@router.post("/{project_id}/users/{user_id}", status_code=204, dependencies=[Depends(require_permission(USERS_MANAGE))])
async def add_user_to_project(
    project_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_project_access),
) -> None:
    link = ProjectUser(project_id=project_id, user_id=user_id, access_level="member")
    db.add(link)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Usuário já vinculado ao projeto.")
