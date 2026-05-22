from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.api.deps import get_current_user, require_permission
from app.database.session import get_db
from app.core.permission_codes import ASSETS_EDIT, ASSETS_VIEW, WORKSPACE_ASSETS_ACCESS
from app.models.asset import AssetAttachmentType, AssetPhysicalCondition, AssetStatus
from app.models.user import User
from app.schemas.assets import (
    AssetAssignmentCreate,
    AssetAssignmentRead,
    AssetAssignmentReturn,
    AssetAssignmentReturnUpdate,
    AssetAttachmentRead,
    AssetCreate,
    AssetDetail,
    AssetInspectionCreate,
    AssetInspectionRead,
    AssetListItem,
    AssetRead,
    AssetUpdate,
)
from app.schemas.assets_dashboard import AssetDashboardRead
from app.services.assets_dashboard_service import AssetsDashboardService
from app.services.assets_service import AssetsService

router = APIRouter()

_read = [Depends(require_permission(ASSETS_VIEW))]
_edit = [Depends(require_permission(ASSETS_EDIT))]
_workspace = [Depends(require_permission(WORKSPACE_ASSETS_ACCESS))]


@router.get("/meta/categories", response_model=list[str], dependencies=_read + _workspace)
async def list_categories() -> list[str]:
    return AssetsService.categories_meta()


@router.get("", response_model=list[AssetListItem], dependencies=_read + _workspace)
async def list_assets(
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
    status: AssetStatus | None = Query(default=None),
    employee_id: UUID | None = Query(default=None),
    cost_center_ref: str | None = Query(default=None),
    expiration: str | None = Query(default=None, description="expired | 30 | 7 | tomorrow"),
    size: str | None = Query(default=None),
    without_holder: bool | None = Query(default=None),
    physical_condition: AssetPhysicalCondition | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[AssetListItem]:
    svc = AssetsService(db)
    return await svc.list_assets(
        q=q,
        category=category,
        status=status,
        employee_id=employee_id,
        cost_center_ref=cost_center_ref,
        expiration=expiration,
        size=size,
        without_holder=without_holder,
        physical_condition=physical_condition,
    )


@router.get("/dashboard", response_model=AssetDashboardRead, dependencies=_read + _workspace)
async def assets_dashboard(db: AsyncSession = Depends(get_db)) -> AssetDashboardRead:
    return await AssetsDashboardService(db).get_dashboard()


@router.post("", response_model=AssetRead, dependencies=_edit + _workspace)
async def create_asset(payload: AssetCreate, db: AsyncSession = Depends(get_db)) -> AssetRead:
    svc = AssetsService(db)
    try:
        row = await svc.create_asset(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return row


@router.get("/{asset_id}", response_model=AssetDetail, dependencies=_read + _workspace)
async def get_asset_detail(asset_id: UUID, db: AsyncSession = Depends(get_db)) -> AssetDetail:
    svc = AssetsService(db)
    row = await svc.get_detail(asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Ativo não encontrado")
    return row


@router.patch("/{asset_id}", response_model=AssetRead, dependencies=_edit + _workspace)
async def update_asset(
    asset_id: UUID, payload: AssetUpdate, db: AsyncSession = Depends(get_db)
) -> AssetRead:
    svc = AssetsService(db)
    try:
        row = await svc.update_asset(asset_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Ativo não encontrado")
    await db.commit()
    return row


@router.delete("/{asset_id}", status_code=204, dependencies=_edit + _workspace)
async def delete_asset(asset_id: UUID, db: AsyncSession = Depends(get_db)) -> None:
    svc = AssetsService(db)
    ok = await svc.soft_delete_asset(asset_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Ativo não encontrado")
    await db.commit()


@router.delete(
    "/{asset_id}/assignments/{assignment_id}",
    status_code=204,
    dependencies=_edit + _workspace,
)
async def delete_assignment(
    asset_id: UUID, assignment_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    svc = AssetsService(db)
    ok = await svc.soft_delete_assignment(asset_id, assignment_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Movimentação não encontrada")
    await db.commit()


@router.post("/{asset_id}/assignments", response_model=AssetAssignmentRead, dependencies=_edit + _workspace)
async def create_assignment(
    asset_id: UUID, payload: AssetAssignmentCreate, db: AsyncSession = Depends(get_db)
) -> AssetAssignmentRead:
    svc = AssetsService(db)
    try:
        row = await svc.create_assignment(asset_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Ativo não encontrado")
    await db.commit()
    return row


@router.post(
    "/{asset_id}/assignments/{assignment_id}/return",
    response_model=AssetAssignmentRead,
    dependencies=_edit + _workspace,
)
async def return_assignment(
    asset_id: UUID,
    assignment_id: UUID,
    payload: AssetAssignmentReturn,
    db: AsyncSession = Depends(get_db),
) -> AssetAssignmentRead:
    svc = AssetsService(db)
    try:
        row = await svc.return_assignment(asset_id, assignment_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Movimentação não encontrada")
    await db.commit()
    return row


@router.patch(
    "/{asset_id}/assignments/{assignment_id}/return",
    response_model=AssetAssignmentRead,
    dependencies=_edit + _workspace,
)
async def update_return_assignment(
    asset_id: UUID,
    assignment_id: UUID,
    payload: AssetAssignmentReturnUpdate,
    db: AsyncSession = Depends(get_db),
) -> AssetAssignmentRead:
    svc = AssetsService(db)
    try:
        row = await svc.update_return_assignment(asset_id, assignment_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Movimentação não encontrada")
    await db.commit()
    return row


@router.delete(
    "/{asset_id}/assignments/{assignment_id}/return",
    response_model=AssetAssignmentRead,
    dependencies=_edit + _workspace,
)
async def delete_return_assignment(
    asset_id: UUID,
    assignment_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> AssetAssignmentRead:
    svc = AssetsService(db)
    try:
        row = await svc.delete_return_assignment(asset_id, assignment_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Movimentação não encontrada")
    await db.commit()
    return row


@router.delete(
    "/{asset_id}/inspections/{inspection_id}",
    status_code=204,
    dependencies=_edit + _workspace,
)
async def delete_inspection(
    asset_id: UUID, inspection_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    svc = AssetsService(db)
    ok = await svc.soft_delete_inspection(asset_id, inspection_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Ensaio não encontrado")
    await db.commit()


@router.post("/{asset_id}/inspections", response_model=AssetInspectionRead, dependencies=_edit + _workspace)
async def create_inspection(
    asset_id: UUID, payload: AssetInspectionCreate, db: AsyncSession = Depends(get_db)
) -> AssetInspectionRead:
    svc = AssetsService(db)
    row = await svc.create_inspection(asset_id, payload)
    if row is None:
        raise HTTPException(status_code=404, detail="Ativo não encontrado")
    await db.commit()
    return row


@router.post("/{asset_id}/attachments", response_model=AssetAttachmentRead, dependencies=_edit + _workspace)
async def upload_attachment(
    asset_id: UUID,
    file: UploadFile = File(...),
    file_type: AssetAttachmentType = Form(default=AssetAttachmentType.OTHER),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> AssetAttachmentRead:
    body = await file.read()
    if len(body) > settings.asset_upload_max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo excede o limite de {settings.asset_upload_max_bytes // (1024 * 1024)} MB.",
        )
    svc = AssetsService(db)
    row = await svc.save_attachment(
        asset_id,
        file_name=(file.filename or "arquivo").strip(),
        body=body,
        mime_type=file.content_type,
        file_type=file_type,
        uploaded_by_user_id=actor.id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Ativo não encontrado")
    await db.commit()
    return AssetAttachmentRead(
        id=row.id,
        asset_id=row.asset_id,
        file_name=row.file_name,
        file_type=row.file_type,
        mime_type=row.mime_type,
        created_at=row.created_at,
        download_url=f"assets/{asset_id}/attachments/{row.id}/download",
    )


@router.get(
    "/{asset_id}/attachments/{attachment_id}/download",
    dependencies=_read + _workspace,
)
async def download_attachment(
    asset_id: UUID, attachment_id: UUID, db: AsyncSession = Depends(get_db)
) -> FileResponse:
    svc = AssetsService(db)
    row = await svc.get_attachment(asset_id, attachment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Anexo não encontrado")
    path = svc.attachment_disk_path(row)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado no servidor.")
    media = row.mime_type or "application/octet-stream"
    return FileResponse(path, media_type=media, filename=row.file_name)


@router.delete(
    "/{asset_id}/attachments/{attachment_id}",
    status_code=204,
    dependencies=_edit + _workspace,
)
async def delete_attachment(
    asset_id: UUID, attachment_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    svc = AssetsService(db)
    ok = await svc.delete_attachment(asset_id, attachment_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Anexo não encontrado")
    await db.commit()
