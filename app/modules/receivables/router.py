from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from app.api.deps import (
    ensure_project_access,
    get_accessible_project_ids,
    get_current_user,
    require_permission,
    user_sees_all_projects,
)
from app.core.config import settings
from app.core.permission_codes import INVOICES_EDIT, INVOICES_VIEW
from app.database.session import get_db
from app.models.user import User
from app.schemas.receivable import (
    InvoiceAnticipationCreate,
    InvoiceAnticipationRead,
    InvoiceAnticipationUpdate,
    ReceivableInvoiceCreate,
    ReceivableInvoiceRead,
    ReceivableInvoiceUpdate,
    ReceivableKpisRead,
    ReceivableInvoiceFileRead,
)
from app.services.receivable_service import ReceivableService
from app.models.receivable import ReceivableInvoiceFile


def _actor_email(user: User) -> str:
    return user.email


def _pdf_disk_path(stored: str) -> Path:
    base = Path(settings.receivable_upload_dir)
    p = (base / stored).resolve()
    b = base.resolve()
    if b not in p.parents and p != b:
        raise HTTPException(status_code=400, detail="Caminho de arquivo inválido.")
    return p


_read_view = [Depends(require_permission(INVOICES_VIEW))]

invoices_router = APIRouter()


@invoices_router.get("", response_model=list[ReceivableInvoiceRead], dependencies=_read_view)
async def list_invoices(
    project_id: UUID | None = Query(default=None),
    status: str | None = Query(
        default=None,
        pattern="^(EMITIDA|ANTECIPADA|RECEBIDA|CANCELADA)$",
    ),
    client: str | None = Query(default=None, max_length=255),
    period_field: str = Query(
        default="issue",
        pattern="^(issue|due)$",
        description="Filtrar período por data de emissão (issue) ou vencimento (due).",
    ),
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ReceivableInvoiceRead]:
    if (year is None) != (month is None):
        raise HTTPException(status_code=400, detail="Informe ano e mês juntos para o período, ou deixe ambos vazios.")
    svc = ReceivableService(db)
    pf = "issue" if period_field == "issue" else "due"

    async def run_list(pid: UUID | None, pids: list[UUID] | None) -> list[ReceivableInvoiceRead]:
        rows = await svc.list_invoices(
            project_id=pid,
            project_ids=pids,
            status=status,
            client_busca=client,
            year=year,
            month=month,
            period_field=pf,
        )
        prefix = settings.api_v1_prefix.rstrip("/")
        return [
            ReceivableInvoiceRead.model_validate(svc.invoice_to_read(r, api_prefix=prefix))
            for r in rows
        ]

    if not user_sees_all_projects(user):
        allowed = await get_accessible_project_ids(user, db)
        if project_id is not None:
            if project_id not in allowed:
                raise HTTPException(status_code=403, detail="Sem permissão.")
            return await run_list(project_id, None)
        return await run_list(None, allowed)
    return await run_list(project_id, None)


@invoices_router.get("/kpis", response_model=ReceivableKpisRead, dependencies=_read_view)
async def get_kpis(
    project_id: UUID | None = Query(default=None),
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    period_field: str = Query(default="issue", pattern="^(issue|due)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReceivableKpisRead:
    if (year is None) != (month is None):
        raise HTTPException(status_code=400, detail="Informe ano e mês juntos para o período, ou deixe ambos vazios.")
    svc = ReceivableService(db)
    pf = "issue" if period_field == "issue" else "due"
    if not user_sees_all_projects(user):
        allowed = await get_accessible_project_ids(user, db)
        if project_id is not None:
            if project_id not in allowed:
                raise HTTPException(status_code=403, detail="Sem permissão.")
            data = await svc.kpis(project_id=project_id, project_ids=None, year=year, month=month, period_field=pf)
        else:
            data = await svc.kpis(project_id=None, project_ids=allowed, year=year, month=month, period_field=pf)
    else:
        data = await svc.kpis(project_id=project_id, project_ids=None, year=year, month=month, period_field=pf)
    return ReceivableKpisRead.model_validate(data)


@invoices_router.post("", response_model=ReceivableInvoiceRead, dependencies=[Depends(require_permission(INVOICES_EDIT))])
async def create_invoice(
    payload: ReceivableInvoiceCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> ReceivableInvoiceRead:
    await ensure_project_access(user=actor, project_id=payload.project_id, db=db)
    svc = ReceivableService(db)
    row = await svc.create_invoice(payload.model_dump(), log_user=_actor_email(actor))
    await db.commit()
    loaded = await svc.get_invoice(row.id)
    if loaded is None:
        raise HTTPException(status_code=500, detail="Falha ao carregar NF")
    prefix = settings.api_v1_prefix.rstrip("/")
    return ReceivableInvoiceRead.model_validate(svc.invoice_to_read(loaded, api_prefix=prefix))


@invoices_router.patch("/{invoice_id}", response_model=ReceivableInvoiceRead, dependencies=[Depends(require_permission(INVOICES_EDIT))])
async def update_invoice(
    invoice_id: UUID,
    payload: ReceivableInvoiceUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> ReceivableInvoiceRead:
    svc = ReceivableService(db)
    inv = await svc.get_invoice(invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    await ensure_project_access(user=actor, project_id=inv.project_id, db=db)
    data = payload.model_dump(exclude_unset=True)
    try:
        row = await svc.update_invoice(invoice_id, data, log_user=_actor_email(actor))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if row is None:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    await db.commit()
    loaded = await svc.get_invoice(invoice_id)
    if loaded is None:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    prefix = settings.api_v1_prefix.rstrip("/")
    return ReceivableInvoiceRead.model_validate(svc.invoice_to_read(loaded, api_prefix=prefix))


@invoices_router.delete("/{invoice_id}", status_code=204, dependencies=[Depends(require_permission(INVOICES_EDIT))])
async def delete_invoice(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> None:
    svc = ReceivableService(db)
    inv = await svc.get_invoice(invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    await ensure_project_access(user=actor, project_id=inv.project_id, db=db)
    if inv.pdf_path:
        p = _pdf_disk_path(inv.pdf_path)
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass
    ok = await svc.delete_invoice(invoice_id)
    if not ok:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    await db.commit()


@invoices_router.post(
    "/{invoice_id}/anticipations",
    response_model=InvoiceAnticipationRead,
    dependencies=[Depends(require_permission(INVOICES_EDIT))],
)
async def add_anticipation(
    invoice_id: UUID,
    payload: InvoiceAnticipationCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> InvoiceAnticipationRead:
    svc = ReceivableService(db)
    inv = await svc.get_invoice(invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    await ensure_project_access(user=actor, project_id=inv.project_id, db=db)
    try:
        row = await svc.add_anticipation(
            invoice_id=invoice_id,
            institution=payload.institution,
            amount_received=payload.amount_received,
            amount_to_repay=payload.amount_to_repay,
            received_date=payload.data_recebimento,
            due_date=payload.due_date,
            log_user=_actor_email(actor),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await db.commit()
    # Resposta mapeada para expor `data_recebimento` (API).
    return InvoiceAnticipationRead.model_validate(
        {
            "id": row.id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "invoice_id": row.invoice_id,
            "institution": row.institution,
            "amount_received": float(row.amount_received or 0),
            "amount_to_repay": float(row.amount_to_repay or 0),
            "data_recebimento": getattr(row, "received_date", None),
            "due_date": row.due_date,
        }
    )


@invoices_router.delete(
    "/{invoice_id}/anticipations/{anticipation_id}",
    status_code=204,
    dependencies=[Depends(require_permission(INVOICES_EDIT))],
)
async def delete_anticipation(
    invoice_id: UUID,
    anticipation_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> None:
    svc = ReceivableService(db)
    inv = await svc.get_invoice(invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    await ensure_project_access(user=actor, project_id=inv.project_id, db=db)
    ok = await svc.delete_anticipation(
        invoice_id=invoice_id,
        anticipation_id=anticipation_id,
        log_user=_actor_email(actor),
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Antecipação não encontrada")
    await db.commit()


@invoices_router.patch(
    "/{invoice_id}/anticipations/{anticipation_id}",
    response_model=InvoiceAnticipationRead,
    dependencies=[Depends(require_permission(INVOICES_EDIT))],
)
async def update_anticipation(
    invoice_id: UUID,
    anticipation_id: UUID,
    payload: InvoiceAnticipationUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> InvoiceAnticipationRead:
    svc = ReceivableService(db)
    inv = await svc.get_invoice(invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    await ensure_project_access(user=actor, project_id=inv.project_id, db=db)
    try:
        row = await svc.update_anticipation(
            invoice_id=invoice_id,
            anticipation_id=anticipation_id,
            institution=payload.institution,
            amount_received=payload.amount_received,
            amount_to_repay=payload.amount_to_repay,
            received_date=payload.data_recebimento,
            due_date=payload.due_date,
            log_user=_actor_email(actor),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if row is None:
        raise HTTPException(status_code=404, detail="Antecipação não encontrada")
    await db.commit()
    return InvoiceAnticipationRead.model_validate(
        {
            "id": row.id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "invoice_id": row.invoice_id,
            "institution": row.institution,
            "amount_received": float(row.amount_received or 0),
            "amount_to_repay": float(row.amount_to_repay or 0),
            "data_recebimento": getattr(row, "received_date", None),
            "due_date": row.due_date,
        }
    )


@invoices_router.get("/{invoice_id}/pdf", dependencies=_read_view)
async def download_invoice_pdf(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    svc = ReceivableService(db)
    inv = await svc.get_invoice(invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    await ensure_project_access(user=user, project_id=inv.project_id, db=db)
    if not inv.pdf_path:
        raise HTTPException(status_code=404, detail="Nenhum PDF anexado.")
    path = _pdf_disk_path(inv.pdf_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado no servidor.")
    safe_name = f"NF-{inv.nf_number.replace('/', '-')}.pdf"
    return FileResponse(path, media_type="application/pdf", filename=safe_name)


@invoices_router.post("/{invoice_id}/pdf", dependencies=[Depends(require_permission(INVOICES_EDIT))])
async def upload_invoice_pdf(
    invoice_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> ReceivableInvoiceRead:
    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(status_code=400, detail="Envie apenas arquivo PDF.")
    svc = ReceivableService(db)
    inv = await svc.get_invoice(invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    await ensure_project_access(user=actor, project_id=inv.project_id, db=db)
    # Limite de 3 arquivos por NF.
    existing_count = int(
        (
            await db.execute(
                select(func.count()).select_from(ReceivableInvoiceFile).where(
                    ReceivableInvoiceFile.invoice_id == invoice_id
                )
            )
        ).scalar_one()
        or 0
    )
    if existing_count >= 3:
        raise HTTPException(status_code=409, detail="Limite de 3 PDFs por NF atingido.")

    body = await file.read()
    if len(body) > settings.receivable_pdf_max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"PDF excede o limite de {settings.receivable_pdf_max_bytes // (1024 * 1024)} MB.",
        )
    if not body.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="O arquivo não parece ser um PDF válido.")
    # Salva em disco: uploads/invoices/{invoice_id}/{file_id}.pdf
    base = Path(settings.receivable_upload_dir) / "invoices" / str(invoice_id)
    base.mkdir(parents=True, exist_ok=True)
    original_name = (file.filename or "documento.pdf").strip()[:255]
    file_id = uuid4()
    stored_name = f"{file_id}.pdf"
    dest = (base / stored_name).resolve()
    dest.write_bytes(body)
    rel = str(dest.relative_to(Path(settings.receivable_upload_dir).resolve()))

    db.add(
        ReceivableInvoiceFile(
            id=file_id,
            invoice_id=invoice_id,
            file_name=original_name,
            stored_path=rel,
            content_type=file.content_type or "application/pdf",
            size_bytes=len(body),
        )
    )
    await db.flush()
    # Mantém compatibilidade: pdf_path aponta para o último anexado.
    row = await svc.set_pdf_path(invoice_id, rel, log_user=_actor_email(actor))
    if row is None:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    await db.commit()
    loaded = await svc.get_invoice(invoice_id)
    if loaded is None:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    prefix = settings.api_v1_prefix.rstrip("/")
    return ReceivableInvoiceRead.model_validate(svc.invoice_to_read(loaded, api_prefix=prefix))


@invoices_router.get("/{invoice_id}/files", response_model=list[ReceivableInvoiceFileRead], dependencies=_read_view)
async def list_invoice_files(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ReceivableInvoiceFileRead]:
    svc = ReceivableService(db)
    inv = await svc.get_invoice(invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    await ensure_project_access(user=user, project_id=inv.project_id, db=db)
    stmt = (
        select(ReceivableInvoiceFile)
        .where(ReceivableInvoiceFile.invoice_id == invoice_id)
        .order_by(ReceivableInvoiceFile.created_at.asc())
    )
    rows = list((await db.execute(stmt)).scalars().all())
    return [
        ReceivableInvoiceFileRead(
            id=r.id,
            created_at=r.created_at,
            updated_at=r.updated_at,
            invoice_id=r.invoice_id,
            file_name=r.file_name,
            content_type=r.content_type,
            size_bytes=int(r.size_bytes or 0),
        )
        for r in rows
    ]


@invoices_router.get("/{invoice_id}/files/{file_id}", dependencies=_read_view)
async def download_invoice_file(
    invoice_id: UUID,
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    svc = ReceivableService(db)
    inv = await svc.get_invoice(invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    await ensure_project_access(user=user, project_id=inv.project_id, db=db)
    row = await db.get(ReceivableInvoiceFile, file_id)
    if row is None or row.invoice_id != invoice_id:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    path = _pdf_disk_path(row.stored_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado no servidor.")
    safe = (row.file_name or f"NF-{inv.nf_number.replace('/', '-')}.pdf").replace("/", "-")
    return FileResponse(path, media_type=row.content_type or "application/pdf", filename=safe)


@invoices_router.delete("/{invoice_id}/pdf", response_model=ReceivableInvoiceRead, dependencies=[Depends(require_permission(INVOICES_EDIT))])
async def delete_invoice_pdf(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> ReceivableInvoiceRead:
    svc = ReceivableService(db)
    inv = await svc.get_invoice(invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    await ensure_project_access(user=actor, project_id=inv.project_id, db=db)
    # Remove todos arquivos vinculados à NF (até 3) e o diretório.
    stmt = select(ReceivableInvoiceFile).where(ReceivableInvoiceFile.invoice_id == invoice_id)
    rows = list((await db.execute(stmt)).scalars().all())
    for r in rows:
        try:
            p = _pdf_disk_path(r.stored_path)
            if p.is_file():
                p.unlink()
        except OSError:
            pass
        except HTTPException:
            pass
        await db.delete(r)
    # tenta remover o diretório da NF (se vazio)
    try:
        (Path(settings.receivable_upload_dir) / "invoices" / str(invoice_id)).rmdir()
    except OSError:
        pass
    row = await svc.clear_pdf(invoice_id, log_user=_actor_email(actor))
    if row is None:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    await db.commit()
    loaded = await svc.get_invoice(invoice_id)
    if loaded is None:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    prefix = settings.api_v1_prefix.rstrip("/")
    return ReceivableInvoiceRead.model_validate(svc.invoice_to_read(loaded, api_prefix=prefix))
