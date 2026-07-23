from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.api.deps import get_current_user, require_permission, user_has_permission
from app.api.sensitive import ASSET_SENSITIVE_FIELDS, redact
from app.database.session import get_db
from app.core.permission_codes import (
    ASSETS_CREATE,
    ASSETS_DELETE,
    ASSETS_LIST,
    ASSETS_READ,
    ASSETS_SENSITIVE,
    ASSETS_UPDATE,
    WORKSPACE_ASSETS_ACCESS,
)
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

# Modelo de verbos (Fase 2). Listagens → assets.list; detalhe/leitura → assets.read;
# criar/editar/excluir o ativo → create/update/delete; mutações de sub-recursos (movimentações,
# ensaios, anexos) → assets.update (gerenciam os dados do ativo, não excluem o ativo).
_list = [Depends(require_permission(ASSETS_LIST))]
_read = [Depends(require_permission(ASSETS_READ))]
_create = [Depends(require_permission(ASSETS_CREATE))]
_update = [Depends(require_permission(ASSETS_UPDATE))]
_delete = [Depends(require_permission(ASSETS_DELETE))]
_workspace = [Depends(require_permission(WORKSPACE_ASSETS_ACCESS))]


def _redact_dashboard(d: AssetDashboardRead) -> AssetDashboardRead:
    """Omite (zera) TODOS os agregados MONETÁRIOS do dashboard patrimonial, preservando as
    quantidades (count/asset_count/damaged_count). Usado quando o usuário não tem assets.sensitive:
    o backend deixa de enviar valores (valor total/em uso/disponível/manutenção/perdido, valor por
    categoria/estado físico e valor por centro de custo)."""
    zero_cv = lambda cv: cv.model_copy(update={"value": 0.0})
    status = d.status.model_copy(
        update={
            "total": zero_cv(d.status.total),
            "in_use": zero_cv(d.status.in_use),
            "available": zero_cv(d.status.available),
            "maintenance": zero_cv(d.status.maintenance),
            "lost_or_discarded": zero_cv(d.status.lost_or_discarded),
        }
    )
    alerts = d.alerts.model_copy(
        update={
            "expired_inspections": d.alerts.expired_inspections.model_copy(update={"amount_total": 0.0}),
            "expiring_inspections": d.alerts.expiring_inspections.model_copy(update={"amount_total": 0.0}),
            "without_holder": d.alerts.without_holder.model_copy(update={"amount_total": 0.0}),
            "fair_condition": d.alerts.fair_condition.model_copy(update={"amount_total": 0.0}),
        }
    )
    return d.model_copy(
        update={
            "status": status,
            "physical_condition": [r.model_copy(update={"value": 0.0}) for r in d.physical_condition],
            "by_category": [r.model_copy(update={"value": 0.0}) for r in d.by_category],
            "by_cost_center": [
                r.model_copy(update={"amount_total": 0.0, "average_value": 0.0}) for r in d.by_cost_center
            ],
            "alerts": alerts,
        }
    )


@router.get("/meta/categories", response_model=list[str], dependencies=_list + _workspace)
async def list_categories(
    scope: str | None = Query(default=None, description="patrimonial | epi | all (default all)"),
) -> list[str]:
    return AssetsService.categories_meta(scope=scope)


@router.get("", response_model=list[AssetListItem], dependencies=_list + _workspace)
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
    exclude_epi: bool = Query(default=False, description="Excluir categoria EPI (patrimônio)"),
    only_epi: bool = Query(default=False, description="Somente categoria EPI"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AssetListItem]:
    svc = AssetsService(db)
    rows = await svc.list_assets(
        q=q,
        category=category,
        status=status,
        employee_id=employee_id,
        cost_center_ref=cost_center_ref,
        expiration=expiration,
        size=size,
        without_holder=without_holder,
        physical_condition=physical_condition,
        exclude_epi=exclude_epi,
        only_epi=only_epi,
    )
    _inc = user_has_permission(user, ASSETS_SENSITIVE)
    return [redact(r, ASSET_SENSITIVE_FIELDS, _inc) for r in rows]


@router.get("/epis", response_model=list[AssetListItem], dependencies=_list + _workspace)
async def list_epis(
    q: str | None = Query(default=None),
    status: AssetStatus | None = Query(default=None),
    employee_id: UUID | None = Query(default=None),
    cost_center_ref: str | None = Query(default=None),
    expiration: str | None = Query(default=None, description="expired | 30 | 7 | tomorrow"),
    size: str | None = Query(default=None),
    without_holder: bool | None = Query(default=None),
    physical_condition: AssetPhysicalCondition | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AssetListItem]:
    """Listagem operacional de EPIs (mesma tabela `assets`, escopo EPI)."""
    svc = AssetsService(db)
    rows = await svc.list_assets(
        q=q,
        status=status,
        employee_id=employee_id,
        cost_center_ref=cost_center_ref,
        expiration=expiration,
        size=size,
        without_holder=without_holder,
        physical_condition=physical_condition,
        only_epi=True,
    )
    _inc = user_has_permission(user, ASSETS_SENSITIVE)
    return [redact(r, ASSET_SENSITIVE_FIELDS, _inc) for r in rows]


@router.get("/dashboard", response_model=AssetDashboardRead, dependencies=_read + _workspace)
async def assets_dashboard(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> AssetDashboardRead:
    dash = await AssetsDashboardService(db).get_dashboard()
    # Sem assets.sensitive: omite os valores monetários dos cards/gráficos (mantém as quantidades).
    if not user_has_permission(user, ASSETS_SENSITIVE):
        dash = _redact_dashboard(dash)
    return dash


@router.post("", response_model=AssetRead, dependencies=_create + _workspace)
async def create_asset(
    payload: AssetCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> AssetRead:
    svc = AssetsService(db)
    try:
        row = await svc.create_asset(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    # Criar NÃO concede ver: sem assets.sensitive, o valor recém-cadastrado volta omitido.
    return redact(row, ASSET_SENSITIVE_FIELDS, user_has_permission(user, ASSETS_SENSITIVE))


@router.get("/{asset_id}", response_model=AssetDetail, dependencies=_read + _workspace)
async def get_asset_detail(
    asset_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> AssetDetail:
    svc = AssetsService(db)
    row = await svc.get_detail(asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Ativo não encontrado")
    return redact(row, ASSET_SENSITIVE_FIELDS, user_has_permission(user, ASSETS_SENSITIVE))


@router.patch("/{asset_id}", response_model=AssetRead, dependencies=_update + _workspace)
async def update_asset(
    asset_id: UUID,
    payload: AssetUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AssetRead:
    svc = AssetsService(db)
    try:
        row = await svc.update_asset(asset_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Ativo não encontrado")
    await db.commit()
    # Editar NÃO concede ver: sem assets.sensitive, o valor salvo volta omitido.
    return redact(row, ASSET_SENSITIVE_FIELDS, user_has_permission(user, ASSETS_SENSITIVE))


@router.delete("/{asset_id}", status_code=204, dependencies=_delete + _workspace)
async def delete_asset(asset_id: UUID, db: AsyncSession = Depends(get_db)) -> None:
    svc = AssetsService(db)
    ok = await svc.soft_delete_asset(asset_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Ativo não encontrado")
    await db.commit()


@router.delete(
    "/{asset_id}/assignments/{assignment_id}",
    status_code=204,
    dependencies=_update + _workspace,
)
async def delete_assignment(
    asset_id: UUID, assignment_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    svc = AssetsService(db)
    ok = await svc.soft_delete_assignment(asset_id, assignment_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Movimentação não encontrada")
    await db.commit()


@router.post("/{asset_id}/assignments", response_model=AssetAssignmentRead, dependencies=_update + _workspace)
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
    dependencies=_update + _workspace,
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
    dependencies=_update + _workspace,
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
    dependencies=_update + _workspace,
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
    dependencies=_update + _workspace,
)
async def delete_inspection(
    asset_id: UUID, inspection_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    svc = AssetsService(db)
    ok = await svc.soft_delete_inspection(asset_id, inspection_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Ensaio não encontrado")
    await db.commit()


@router.post("/{asset_id}/inspections", response_model=AssetInspectionRead, dependencies=_update + _workspace)
async def create_inspection(
    asset_id: UUID, payload: AssetInspectionCreate, db: AsyncSession = Depends(get_db)
) -> AssetInspectionRead:
    svc = AssetsService(db)
    row = await svc.create_inspection(asset_id, payload)
    if row is None:
        raise HTTPException(status_code=404, detail="Ativo não encontrado")
    await db.commit()
    return row


@router.post("/{asset_id}/attachments", response_model=AssetAttachmentRead, dependencies=_update + _workspace)
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
    dependencies=_update + _workspace,
)
async def delete_attachment(
    asset_id: UUID, attachment_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    svc = AssetsService(db)
    ok = await svc.delete_attachment(asset_id, attachment_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Anexo não encontrado")
    await db.commit()
