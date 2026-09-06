from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permission, user_has_any_permission
from app.core.permission_codes import (
    COMPANY_FINANCE_READ,
    COMPANY_FINANCE_UPDATE,
    PROJECTS_READ,
    PROJECTS_UPDATE,
)
from app.database.session import get_db
from app.models.user import User
from app.schemas.payment_variable_component import (
    PaymentComponentAttachmentRead,
    PaymentVariableComponentCreate,
    PaymentVariableComponentRead,
    PaymentVariableComponentUpdate,
    VariableComponentReplace,
)
from app.services.payment_component_attachment_service import PaymentComponentAttachmentService
from app.utils.media_type import resolve_media_type
from app.services.payment_variable_component_service import PaymentVariableComponentService

router = APIRouter()

# Leitura/edição exige a permissão do CONTEXTO (isolamento de módulos): Projeto usa
# projects.*; Custo Fixo usa company_finance.*. O gate do endpoint aceita qualquer um dos
# dois; o handler refina pelo contexto do lançamento.
_READ_ANY = [Depends(require_permission(PROJECTS_READ, COMPANY_FINANCE_READ))]
_EDIT_ANY = [Depends(require_permission(PROJECTS_UPDATE, COMPANY_FINANCE_UPDATE))]


def _require_project_ctx(user: User) -> None:
    if not user_has_any_permission(user, PROJECTS_UPDATE):
        raise HTTPException(status_code=403, detail="Sem permissão para editar componentes de projeto.")


def _require_fixed_ctx(user: User) -> None:
    if not user_has_any_permission(user, COMPANY_FINANCE_UPDATE):
        raise HTTPException(status_code=403, detail="Sem permissão para editar componentes de custo fixo.")


@router.get("", response_model=list[PaymentVariableComponentRead], dependencies=_READ_ANY)
async def list_variable_components(
    project_labor_id: UUID | None = Query(default=None),
    company_financial_item_id: UUID | None = Query(default=None),
    competencia: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[PaymentVariableComponentRead]:
    svc = PaymentVariableComponentService(db)
    if project_labor_id is not None:
        rows = await svc.list_for_project_labor(project_labor_id)
    elif company_financial_item_id is not None and competencia is not None:
        rows = await svc.list_for_company_item(company_financial_item_id, competencia)
    else:
        raise HTTPException(
            status_code=400,
            detail="Informe project_labor_id OU (company_financial_item_id + competencia).",
        )
    return [PaymentVariableComponentRead.model_validate(r) for r in rows]


@router.post("", response_model=PaymentVariableComponentRead, dependencies=_EDIT_ANY)
async def create_variable_component(
    payload: PaymentVariableComponentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PaymentVariableComponentRead:
    if payload.project_labor_id is not None:
        _require_project_ctx(user)
    else:
        _require_fixed_ctx(user)
    svc = PaymentVariableComponentService(db)
    row = await svc.create(payload.model_dump())
    await db.commit()  # transação única: componente + snapshot
    return PaymentVariableComponentRead.model_validate(row)


@router.patch("/{component_id}", response_model=PaymentVariableComponentRead, dependencies=_EDIT_ANY)
async def update_variable_component(
    component_id: UUID,
    payload: PaymentVariableComponentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PaymentVariableComponentRead:
    svc = PaymentVariableComponentService(db)
    current = await svc.get(component_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Componente não encontrado.")
    if current.project_labor_id is not None:
        _require_project_ctx(user)
    else:
        _require_fixed_ctx(user)
    row = await svc.update(component_id, payload.model_dump(exclude_unset=True))
    await db.commit()
    return PaymentVariableComponentRead.model_validate(row)


@router.put(
    "/project-labor/{labor_id}",
    response_model=list[PaymentVariableComponentRead],
    dependencies=_EDIT_ANY,
)
async def replace_project_labor_components(
    labor_id: UUID,
    payload: VariableComponentReplace,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PaymentVariableComponentRead]:
    """Salva o conjunto completo de componentes do vínculo em UMA operação (transação única)."""
    _require_project_ctx(user)
    svc = PaymentVariableComponentService(db)
    rows = await svc.replace_for_project_labor(labor_id, [i.model_dump() for i in payload.items])
    await db.commit()
    return [PaymentVariableComponentRead.model_validate(r) for r in rows]


@router.put(
    "/company-item/{item_id}",
    response_model=list[PaymentVariableComponentRead],
    dependencies=_EDIT_ANY,
)
async def replace_company_item_components(
    item_id: UUID,
    payload: VariableComponentReplace,
    competencia: date = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PaymentVariableComponentRead]:
    """Salva o conjunto de componentes do item de Custo Fixo na competência (transação única)."""
    _require_fixed_ctx(user)
    svc = PaymentVariableComponentService(db)
    rows = await svc.replace_for_company_item(
        item_id, competencia, [i.model_dump() for i in payload.items]
    )
    await db.commit()
    return [PaymentVariableComponentRead.model_validate(r) for r in rows]


@router.delete("/{component_id}", status_code=204, dependencies=_EDIT_ANY)
async def delete_variable_component(
    component_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    svc = PaymentVariableComponentService(db)
    current = await svc.get(component_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Componente não encontrado.")
    if current.project_labor_id is not None:
        _require_project_ctx(user)
    else:
        _require_fixed_ctx(user)
    await svc.delete(component_id)
    await db.commit()


# ---------------------------------------------------------------- comprovantes
#
# Anexos do lançamento (nota do reembolso, recibo, cupom). Ficam presos ao COMPONENTE,
# então as duas telas de lançamento — Custos do Projeto e Custos Fixos — usam os mesmos
# endpoints; quem decide a permissão é o contexto do componente, como no CRUD acima.
#
# Anexar/remover comprovante é permitido mesmo depois do lançamento pago: o comprovante
# costuma chegar DEPOIS do pagamento e não altera valor nem identidade do título.


async def _require_ctx_permission(svc: PaymentVariableComponentService, component_id: UUID, user: User):
    current = await svc.get(component_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Componente não encontrado.")
    if current.project_labor_id is not None:
        _require_project_ctx(user)
    else:
        _require_fixed_ctx(user)
    return current


@router.get(
    "/{component_id}/attachments",
    response_model=list[PaymentComponentAttachmentRead],
    dependencies=_READ_ANY,
)
async def list_attachments(
    component_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[PaymentComponentAttachmentRead]:
    svc = PaymentVariableComponentService(db)
    if await svc.get(component_id) is None:
        raise HTTPException(status_code=404, detail="Componente não encontrado.")
    rows = await PaymentComponentAttachmentService(db).list_for_component(component_id)
    return [PaymentComponentAttachmentRead.model_validate(r) for r in rows]


@router.post(
    "/{component_id}/attachments",
    response_model=list[PaymentComponentAttachmentRead],
    dependencies=_EDIT_ANY,
)
async def upload_attachments(
    component_id: UUID,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PaymentComponentAttachmentRead]:
    """Recebe VÁRIOS arquivos de uma vez (o painel da tela permite soltar um lote).

    Tudo ou nada: se um arquivo for recusado (formato/tamanho), nenhum é gravado — o
    usuário corrige e reenvia o lote, em vez de descobrir depois que faltou um.
    """
    svc = PaymentVariableComponentService(db)
    await _require_ctx_permission(svc, component_id, user)
    uploads = [
        ((f.filename or "comprovante"), await f.read(), f.content_type) for f in files
    ]
    out = await PaymentComponentAttachmentService(db).save_many(
        component_id, uploads=uploads, uploaded_by_user_id=user.id
    )
    await db.commit()
    return [PaymentComponentAttachmentRead.model_validate(r) for r in out]


@router.get("/{component_id}/attachments/{attachment_id}/download", dependencies=_READ_ANY)
async def download_attachment(
    component_id: UUID,
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    attachments = PaymentComponentAttachmentService(db)
    row = await attachments.get(component_id, attachment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Comprovante não encontrado.")
    path = attachments.disk_path(row)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado no servidor.")
    # O mime é resolvido pelo nome quando o upload não trouxe um específico — sem isso o
    # navegador baixaria o arquivo em vez de exibi-lo no "Ver".
    return FileResponse(
        path, media_type=resolve_media_type(row.mime_type, row.file_name), filename=row.file_name
    )


@router.delete(
    "/{component_id}/attachments/{attachment_id}", status_code=204, dependencies=_EDIT_ANY
)
async def delete_attachment(
    component_id: UUID,
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    svc = PaymentVariableComponentService(db)
    await _require_ctx_permission(svc, component_id, user)
    if not await PaymentComponentAttachmentService(db).delete(component_id, attachment_id):
        raise HTTPException(status_code=404, detail="Comprovante não encontrado.")
    await db.commit()
