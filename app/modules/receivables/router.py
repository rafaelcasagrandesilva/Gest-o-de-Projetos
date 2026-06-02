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
from app.core.permission_codes import INVOICES_EDIT, INVOICES_REACTIVATE, INVOICES_VIEW
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
from app.schemas.receivable_advance_batch import (
    AdvanceBatchCreate,
    AdvanceBatchEligibleInvoiceRead,
    AdvanceBatchRead,
    AdvanceBatchUpdate,
)
from app.services.receivable_advance_batch_service import ReceivableAdvanceBatchService
from app.services.receivable_service import ReceivableService
from app.models.receivable import ReceivableInvoiceFile


def _actor_email(user: User) -> str:
    return user.email


def _actor_display(user: User) -> str:
    name = (user.full_name or "").strip()
    return name if name else _actor_email(user)


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


@invoices_router.get(
    "/advance-batches/eligible-invoices",
    response_model=list[AdvanceBatchEligibleInvoiceRead],
    dependencies=_read_view,
)
async def list_eligible_invoices_for_batch(
    search: str | None = Query(default=None, max_length=255),
    project_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AdvanceBatchEligibleInvoiceRead]:
    batch_svc = ReceivableAdvanceBatchService(db)
    recv_svc = ReceivableService(db)
    project_ids: list[UUID] | None = None
    if not user_sees_all_projects(user):
        allowed = await get_accessible_project_ids(user, db)
        if project_id is not None:
            if project_id not in allowed:
                raise HTTPException(status_code=403, detail="Sem permissão.")
            project_ids = [project_id]
        else:
            project_ids = allowed
    elif project_id is not None:
        project_ids = [project_id]

    rows = await batch_svc.list_eligible_invoices(project_ids=project_ids, search=search)
    out: list[AdvanceBatchEligibleInvoiceRead] = []
    for inv in rows:
        if project_id is not None and inv.project_id != project_id:
            continue
        if project_ids is not None and inv.project_id not in project_ids:
            continue
        d = recv_svc.invoice_to_read(inv)
        out.append(
            AdvanceBatchEligibleInvoiceRead(
                id=inv.id,
                project_id=inv.project_id,
                project_name=d.get("project_name"),
                number=inv.nf_number,
                client_name=inv.client_name,
                issue_date=inv.issue_date,
                due_date=inv.due_date,
                gross_amount=float(inv.gross_amount),
                net_amount=float(inv.net_amount),
                status=str(d.get("status")),
            )
        )
    return out


@invoices_router.get(
    "/advance-batches",
    response_model=list[AdvanceBatchRead],
    dependencies=_read_view,
)
async def list_advance_batches(
    db: AsyncSession = Depends(get_db),
) -> list[AdvanceBatchRead]:
    batch_svc = ReceivableAdvanceBatchService(db)
    rows = await batch_svc.list_batches()
    return [AdvanceBatchRead.model_validate(batch_svc.batch_to_read(b)) for b in rows]


@invoices_router.get(
    "/advance-batches/{batch_id}",
    response_model=AdvanceBatchRead,
    dependencies=_read_view,
)
async def get_advance_batch(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> AdvanceBatchRead:
    batch_svc = ReceivableAdvanceBatchService(db)
    row = await batch_svc.get_batch(batch_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Borderô não encontrado.")
    return AdvanceBatchRead.model_validate(batch_svc.batch_to_read(row))


@invoices_router.post(
    "/advance-batches",
    response_model=AdvanceBatchRead,
    dependencies=[Depends(require_permission(INVOICES_EDIT))],
)
async def create_advance_batch(
    payload: AdvanceBatchCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> AdvanceBatchRead:
    if not user_sees_all_projects(actor):
        allowed = await get_accessible_project_ids(actor, db)
        for iid in payload.invoice_ids:
            inv = await ReceivableService(db).get_invoice(iid)
            if inv is None:
                raise HTTPException(status_code=404, detail="NF não encontrada.")
            if inv.project_id not in allowed:
                raise HTTPException(status_code=403, detail="Sem permissão para uma ou mais NFs.")

    batch_svc = ReceivableAdvanceBatchService(db)
    try:
        batch = await batch_svc.create_batch(
            operation_type=getattr(payload, "operation_type", "BORDERO"),
            operation_code=getattr(payload, "operation_code", None),
            institution=payload.institution,
            received_amount=payload.received_amount,
            discount_amount=payload.discount_amount,
            fee_amount=payload.fee_amount,
            receive_date=payload.receive_date,
            repayment_date=payload.repayment_date,
            observation=payload.observation,
            invoice_ids=payload.invoice_ids,
            created_by_id=actor.id,
            log_user=_actor_email(actor),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    loaded = await batch_svc.get_batch(batch.id)
    if loaded is None:
        raise HTTPException(status_code=500, detail="Falha ao carregar borderô.")
    return AdvanceBatchRead.model_validate(batch_svc.batch_to_read(loaded))


@invoices_router.patch(
    "/advance-batches/{batch_id}",
    response_model=AdvanceBatchRead,
    dependencies=[Depends(require_permission(INVOICES_EDIT))],
)
async def update_advance_batch(
    batch_id: UUID,
    payload: AdvanceBatchUpdate,
    db: AsyncSession = Depends(get_db),
) -> AdvanceBatchRead:
    batch_svc = ReceivableAdvanceBatchService(db)
    row = await batch_svc.update_dashboard_inclusion(
        batch_id, include_in_dashboard=payload.include_in_dashboard
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Borderô não encontrado.")
    await db.commit()
    loaded = await batch_svc.get_batch(batch_id)
    if loaded is None:
        raise HTTPException(status_code=404, detail="Borderô não encontrado.")
    return AdvanceBatchRead.model_validate(batch_svc.batch_to_read(loaded))


@invoices_router.delete(
    "/advance-batches/{batch_id}",
    status_code=204,
    dependencies=[Depends(require_permission(INVOICES_EDIT))],
)
async def cancel_advance_batch(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> None:
    batch_svc = ReceivableAdvanceBatchService(db)
    try:
        await batch_svc.cancel_batch(batch_id=batch_id, log_user=_actor_email(actor))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()


@invoices_router.delete(
    "/advance-batches/{batch_id}/hard",
    status_code=204,
    dependencies=[Depends(require_permission(INVOICES_EDIT))],
)
async def delete_advance_batch_hard(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> None:
    batch_svc = ReceivableAdvanceBatchService(db)
    try:
        await batch_svc.delete_batch(batch_id=batch_id, log_user=_actor_email(actor))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()


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


@invoices_router.post(
    "/{invoice_id}/reactivate",
    response_model=ReceivableInvoiceRead,
    dependencies=[Depends(require_permission(INVOICES_REACTIVATE))],
)
async def reactivate_invoice(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> ReceivableInvoiceRead:
    svc = ReceivableService(db)
    inv = await svc.get_invoice(invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="NF não encontrada.")
    await ensure_project_access(user=actor, project_id=inv.project_id, db=db)
    try:
        row = await svc.reactivate_invoice(
            invoice_id,
            actor_display=_actor_display(actor),
            log_user=_actor_email(actor),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if row is None:
        raise HTTPException(status_code=404, detail="NF não encontrada.")
    await db.commit()
    loaded = await svc.get_invoice(invoice_id)
    if loaded is None:
        raise HTTPException(status_code=404, detail="NF não encontrada.")
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
            include_in_dashboard=payload.include_in_dashboard,
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
            "include_in_dashboard": bool(getattr(row, "include_in_dashboard", True)),
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
            include_in_dashboard=payload.include_in_dashboard,
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
            "include_in_dashboard": bool(getattr(row, "include_in_dashboard", True)),
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
