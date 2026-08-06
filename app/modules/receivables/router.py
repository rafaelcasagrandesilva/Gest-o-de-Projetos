from __future__ import annotations

from decimal import Decimal
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
from app.core.permission_codes import (
    INVOICES_CREATE,
    INVOICES_LIST,
    INVOICES_REACTIVATE,
    INVOICES_UPDATE,
)
from app.database.session import get_db
from app.api.sensitive import redact_for
from app.models.user import User
from app.schemas.receivable import (
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
from app.schemas.advance_institution import (
    AdvanceInstitutionCreate,
    AdvanceInstitutionRead,
    AdvanceInstitutionUpdate,
)
from app.schemas.advance_settlement import (
    ManagementSummaryRead,
    ObligationRead,
    SettlementCreate,
    SettlementKpisRead,
    TimelineRead,
)
from app.schemas.advance_repasse_ledger import (
    RepasseLedgerEntryRead,
    RepasseLedgerStatementRead,
)
from app.services.advance_institution_service import AdvanceInstitutionService
from app.services.advance_repasse_ledger_service import AdvanceRepasseLedgerService
from app.services.advance_settlement_service import AdvanceSettlementService
from app.services.receivable_advance_batch_service import ReceivableAdvanceBatchService
from app.services.receivable_service import ReceivableService
from app.models.receivable import ReceivableInvoiceFile


def _actor_email(user: User) -> str:
    return user.email


def _actor_display(user: User) -> str:
    name = (user.full_name or "").strip()
    return name if name else _actor_email(user)


async def _invoice_read(
    svc: ReceivableService,
    batch_svc: ReceivableAdvanceBatchService,
    inv,
    prefix: str,
    user: User,
) -> ReceivableInvoiceRead:
    """Monta o read de uma NF já com o histórico N:N (contador + operações).

    Aplica a redação de Dados Sensíveis (invoices.sensitive) — inclusive nas estruturas
    aninhadas (antecipações/lote/histórico) — antes de devolver.
    """
    counts = await batch_svc.confirmed_operation_counts([inv.id])
    history = await batch_svc.invoice_history_map([inv.id])
    return redact_for(
        "invoices",
        ReceivableInvoiceRead.model_validate(
            svc.invoice_to_read(
                inv,
                api_prefix=prefix,
                anticipation_count=counts.get(inv.id, 0),
                advance_operations=history.get(inv.id, []),
            )
        ),
        user,
    )


def _pdf_disk_path(stored: str) -> Path:
    base = Path(settings.receivable_upload_dir)
    p = (base / stored).resolve()
    b = base.resolve()
    if b not in p.parents and p != b:
        raise HTTPException(status_code=400, detail="Caminho de arquivo inválido.")
    return p


_read_view = [Depends(require_permission(INVOICES_LIST))]

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
    official: str = Query(
        default="all",
        pattern="^(all|official|unofficial)$",
        description="Filtra por tipo da NF: all (todas), official (oficiais) ou unofficial (não oficiais).",
    ),
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    competence_year: int | None = Query(default=None, ge=2000, le=2100),
    competence_month: int | None = Query(default=None, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ReceivableInvoiceRead]:
    if (year is None) != (month is None):
        raise HTTPException(status_code=400, detail="Informe ano e mês juntos para o período, ou deixe ambos vazios.")
    if (competence_year is None) != (competence_month is None):
        raise HTTPException(status_code=400, detail="Informe ano e mês juntos para a competência, ou deixe ambos vazios.")
    svc = ReceivableService(db)
    batch_svc = ReceivableAdvanceBatchService(db)
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
            competence_year=competence_year,
            competence_month=competence_month,
            official=official,
        )
        prefix = settings.api_v1_prefix.rstrip("/")
        ids = [r.id for r in rows]
        # Histórico N:N em consultas batelizadas (sem N+1): contador "Antecipada Nx"
        # (regra 7/8) e histórico de operações da NF (regra 5).
        counts = await batch_svc.confirmed_operation_counts(ids)
        history = await batch_svc.invoice_history_map(ids)
        return [
            redact_for(
                "invoices",
                ReceivableInvoiceRead.model_validate(
                    svc.invoice_to_read(
                        r,
                        api_prefix=prefix,
                        anticipation_count=counts.get(r.id, 0),
                        advance_operations=history.get(r.id, []),
                    )
                ),
                user,
            )
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
    status: str | None = Query(default=None, pattern="^(EMITIDA|ANTECIPADA|RECEBIDA|CANCELADA)$"),
    client: str | None = Query(default=None, max_length=255),
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    period_field: str = Query(default="issue", pattern="^(issue|due)$"),
    official: str = Query(default="all", pattern="^(all|official|unofficial)$"),
    competence_year: int | None = Query(default=None, ge=2000, le=2100),
    competence_month: int | None = Query(default=None, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReceivableKpisRead:
    if (year is None) != (month is None):
        raise HTTPException(status_code=400, detail="Informe ano e mês juntos para o período, ou deixe ambos vazios.")
    if (competence_year is None) != (competence_month is None):
        raise HTTPException(status_code=400, detail="Informe ano e mês juntos para a competência, ou deixe ambos vazios.")
    svc = ReceivableService(db)
    pf = "issue" if period_field == "issue" else "due"
    # Mesmos filtros da listagem para que os cards reflitam exatamente o mesmo conjunto.
    common = dict(
        year=year,
        month=month,
        period_field=pf,
        official=official,
        status=status,
        client_busca=client,
        competence_year=competence_year,
        competence_month=competence_month,
    )
    if not user_sees_all_projects(user):
        allowed = await get_accessible_project_ids(user, db)
        if project_id is not None:
            if project_id not in allowed:
                raise HTTPException(status_code=403, detail="Sem permissão.")
            data = await svc.kpis(project_id=project_id, project_ids=None, **common)
        else:
            data = await svc.kpis(project_id=None, project_ids=allowed, **common)
    else:
        data = await svc.kpis(project_id=project_id, project_ids=None, **common)
    return redact_for("invoices_kpis", ReceivableKpisRead.model_validate(data), user)


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
    visible = [
        inv
        for inv in rows
        if (project_id is None or inv.project_id == project_id)
        and (project_ids is None or inv.project_id in project_ids)
    ]
    # Histórico N:N (regra 4): operações válidas em que cada NF já participou, para
    # exibir "Já usada em N operações • LEPTA • DAYCOVAL" sem sumir da seleção.
    ops_map = await batch_svc.operations_for_invoices([inv.id for inv in visible])
    out: list[AdvanceBatchEligibleInvoiceRead] = []
    for inv in visible:
        d = recv_svc.invoice_to_read(inv)
        ops = [batch_svc.operation_summary_entry(b) for b in ops_map.get(inv.id, [])]
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
                operations_count=len(ops),
                operations=ops,  # type: ignore[arg-type]
            )
        )
    return out


# --- Instituições de Antecipação (cadastro próprio do domínio financeiro) ---

_edit_view = [Depends(require_permission(INVOICES_UPDATE))]


@invoices_router.get(
    "/advance-institutions",
    response_model=list[AdvanceInstitutionRead],
    dependencies=_read_view,
)
async def list_advance_institutions(
    only_active: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> list[AdvanceInstitutionRead]:
    svc = AdvanceInstitutionService(db)
    rows = await svc.list(only_active=only_active)
    return [AdvanceInstitutionRead.model_validate(r) for r in rows]


@invoices_router.post(
    "/advance-institutions",
    response_model=AdvanceInstitutionRead,
    dependencies=_edit_view,
)
async def create_advance_institution(
    payload: AdvanceInstitutionCreate,
    db: AsyncSession = Depends(get_db),
) -> AdvanceInstitutionRead:
    svc = AdvanceInstitutionService(db)
    try:
        row = await svc.create(payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return AdvanceInstitutionRead.model_validate(row)


@invoices_router.patch(
    "/advance-institutions/{institution_id}",
    response_model=AdvanceInstitutionRead,
    dependencies=_edit_view,
)
async def update_advance_institution(
    institution_id: UUID,
    payload: AdvanceInstitutionUpdate,
    db: AsyncSession = Depends(get_db),
) -> AdvanceInstitutionRead:
    svc = AdvanceInstitutionService(db)
    try:
        row = await svc.update(institution_id, payload.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if row is None:
        raise HTTPException(status_code=404, detail="Instituição não encontrada.")
    return AdvanceInstitutionRead.model_validate(row)


@invoices_router.delete(
    "/advance-institutions/{institution_id}",
    status_code=204,
    dependencies=_edit_view,
)
async def delete_advance_institution(
    institution_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = AdvanceInstitutionService(db)
    try:
        ok = await svc.delete(institution_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="Instituição não encontrada.")


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
    return [AdvanceBatchRead.model_validate(await batch_svc.batch_read_dict(b)) for b in rows]


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
    return AdvanceBatchRead.model_validate(await batch_svc.batch_read_dict(row))


@invoices_router.post(
    "/advance-batches",
    response_model=AdvanceBatchRead,
    dependencies=[Depends(require_permission(INVOICES_UPDATE))],
)
async def create_advance_batch(
    payload: AdvanceBatchCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> AdvanceBatchRead:
    effective_ids = list(payload.invoice_ids) or [it.invoice_id for it in payload.items]
    if not user_sees_all_projects(actor):
        allowed = await get_accessible_project_ids(actor, db)
        for iid in effective_ids:
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
            institution_id=payload.institution_id,
            received_amount=payload.received_amount,
            discount_amount=payload.discount_amount,
            fee_amount=payload.fee_amount,
            repasse_enabled=payload.repasse_enabled,
            receive_date=payload.receive_date,
            repayment_date=payload.repayment_date,
            observation=payload.observation,
            invoice_ids=payload.invoice_ids,
            items_config=[it.model_dump() for it in payload.items] or None,
            created_by_id=actor.id,
            log_user=_actor_email(actor),
        )
        # A operação já nasce ATIVA: create + confirm numa única transação (elimina o passo
        # de "Confirmar"). Os estados internos DRAFT/OPEN continuam sendo o motor de
        # reverter/reaplicar (usado por editar/cancelar).
        await batch_svc.confirm_batch(batch_id=batch.id, log_user=_actor_email(actor))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    loaded = await batch_svc.get_batch(batch.id)
    if loaded is None:
        raise HTTPException(status_code=500, detail="Falha ao carregar borderô.")
    return AdvanceBatchRead.model_validate(await batch_svc.batch_read_dict(loaded))


@invoices_router.put(
    "/advance-batches/{batch_id}",
    response_model=AdvanceBatchRead,
    dependencies=[Depends(require_permission(INVOICES_UPDATE))],
)
async def edit_advance_batch(
    batch_id: UUID,
    payload: AdvanceBatchCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> AdvanceBatchRead:
    """Edita uma operação ATIVA (reverte → aplica novos dados → reaplica). Bloqueado quando há
    pagamento nas despesas do borderô (só resta cancelar)."""
    effective_ids = list(payload.invoice_ids) or [it.invoice_id for it in payload.items]
    if not user_sees_all_projects(actor):
        allowed = await get_accessible_project_ids(actor, db)
        for iid in effective_ids:
            inv = await ReceivableService(db).get_invoice(iid)
            if inv is None:
                raise HTTPException(status_code=404, detail="NF não encontrada.")
            if inv.project_id not in allowed:
                raise HTTPException(status_code=403, detail="Sem permissão para uma ou mais NFs.")

    batch_svc = ReceivableAdvanceBatchService(db)
    try:
        await batch_svc.edit_batch(
            batch_id=batch_id,
            operation_type=getattr(payload, "operation_type", "BORDERO"),
            operation_code=getattr(payload, "operation_code", None),
            institution_id=payload.institution_id,
            received_amount=payload.received_amount,
            discount_amount=payload.discount_amount,
            fee_amount=payload.fee_amount,
            repasse_enabled=payload.repasse_enabled,
            receive_date=payload.receive_date,
            repayment_date=payload.repayment_date,
            observation=payload.observation,
            invoice_ids=payload.invoice_ids,
            items_config=[it.model_dump() for it in payload.items] or None,
            log_user=_actor_email(actor),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    loaded = await batch_svc.get_batch(batch_id)
    if loaded is None:
        raise HTTPException(status_code=404, detail="Operação não encontrada.")
    return AdvanceBatchRead.model_validate(await batch_svc.batch_read_dict(loaded))


@invoices_router.post(
    "/advance-batches/{batch_id}/confirm",
    response_model=AdvanceBatchRead,
    dependencies=[Depends(require_permission(INVOICES_UPDATE))],
)
async def confirm_advance_batch(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> AdvanceBatchRead:
    batch_svc = ReceivableAdvanceBatchService(db)
    try:
        await batch_svc.confirm_batch(batch_id=batch_id, log_user=_actor_email(actor))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    loaded = await batch_svc.get_batch(batch_id)
    if loaded is None:
        raise HTTPException(status_code=404, detail="Operação não encontrada.")
    return AdvanceBatchRead.model_validate(await batch_svc.batch_read_dict(loaded))


@invoices_router.patch(
    "/advance-batches/{batch_id}",
    response_model=AdvanceBatchRead,
    dependencies=[Depends(require_permission(INVOICES_UPDATE))],
)
async def update_advance_batch(
    batch_id: UUID,
    payload: AdvanceBatchUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> AdvanceBatchRead:
    batch_svc = ReceivableAdvanceBatchService(db)
    row = None
    try:
        if payload.actual_received_amount is not None:
            row = await batch_svc.set_actual_received(
                batch_id=batch_id,
                actual=payload.actual_received_amount,
                log_user=_actor_email(actor),
            )
        if payload.include_in_dashboard is not None:
            row = await batch_svc.update_dashboard_inclusion(
                batch_id, include_in_dashboard=payload.include_in_dashboard
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        # Nenhum campo informado ou operação inexistente — valida existência.
        row = await batch_svc.get_batch(batch_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Borderô não encontrado.")
    await db.commit()
    loaded = await batch_svc.get_batch(batch_id)
    if loaded is None:
        raise HTTPException(status_code=404, detail="Borderô não encontrado.")
    return AdvanceBatchRead.model_validate(await batch_svc.batch_read_dict(loaded))


@invoices_router.delete(
    "/advance-batches/{batch_id}",
    status_code=204,
    dependencies=[Depends(require_permission(INVOICES_UPDATE))],
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
    dependencies=[Depends(require_permission(INVOICES_UPDATE))],
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


# ============================================================================
# Liquidação de NFs antecipadas + Ledger de Repasse (Fase 1A — infraestrutura).
# DORMENTE: novos endpoints, sem qualquer integração com o fluxo atual da LEPTA.
# ============================================================================


@invoices_router.get(
    "/advance-settlements/kpis",
    response_model=SettlementKpisRead,
    dependencies=_read_view,
)
async def advance_settlements_kpis(
    institution_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> SettlementKpisRead:
    svc = AdvanceSettlementService(db)
    return SettlementKpisRead.model_validate(await svc.kpis(institution_id=institution_id))


@invoices_router.get(
    "/advance-settlements/management-summary",
    response_model=ManagementSummaryRead,
    dependencies=_read_view,
)
async def advance_settlements_management_summary(
    institution_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> ManagementSummaryRead:
    svc = AdvanceSettlementService(db)
    return ManagementSummaryRead.model_validate(await svc.management_summary(institution_id=institution_id))


@invoices_router.get(
    "/advance-settlements/{batch_item_id}/timeline",
    response_model=TimelineRead,
    dependencies=_read_view,
)
async def advance_settlement_timeline(
    batch_item_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> TimelineRead:
    svc = AdvanceSettlementService(db)
    try:
        return TimelineRead.model_validate(await svc.obligation_timeline(batch_item_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@invoices_router.get(
    "/advance-settlements",
    response_model=list[ObligationRead],
    dependencies=_read_view,
)
async def list_advance_settlements(
    institution_id: UUID | None = Query(default=None),
    invoice_number: str | None = Query(default=None),
    sgc_number: int | None = Query(default=None),
    situacao: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[ObligationRead]:
    svc = AdvanceSettlementService(db)
    rows = await svc.list_obligations(
        institution_id=institution_id,
        invoice_number=invoice_number,
        sgc_number=sgc_number,
        situacao=situacao,
    )
    return [ObligationRead.model_validate(r) for r in rows]


@invoices_router.post(
    "/advance-settlements",
    response_model=ObligationRead,
    dependencies=[Depends(require_permission(INVOICES_UPDATE))],
)
async def create_advance_settlement(
    payload: SettlementCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> ObligationRead:
    svc = AdvanceSettlementService(db)
    try:
        obligation = await svc.add_movements(
            batch_item_id=payload.batch_item_id,
            movements=[m.model_dump() for m in payload.movements],
            created_by_id=actor.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return ObligationRead.model_validate(obligation)


@invoices_router.delete(
    "/advance-settlement-movements/{movement_id}",
    response_model=ObligationRead,
    dependencies=[Depends(require_permission(INVOICES_UPDATE))],
)
async def reverse_advance_settlement_movement(
    movement_id: UUID,
    reason: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> ObligationRead:
    """Estorna (soft) uma movimentação de liquidação — nunca exclui. Reabre o residual."""
    svc = AdvanceSettlementService(db)
    try:
        obligation = await svc.reverse_movement(movement_id=movement_id, reason=reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return ObligationRead.model_validate(obligation)


@invoices_router.get("/advance-settlements/history/invoice/{invoice_id}", dependencies=_read_view)
async def advance_settlement_invoice_history(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Auditoria: histórico completo de liquidações de uma NF (todas as participações)."""
    return await AdvanceSettlementService(db).invoice_history(invoice_id)


@invoices_router.get("/advance-settlements/history/batch/{batch_id}", dependencies=_read_view)
async def advance_settlement_batch_history(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Auditoria: histórico completo de um borderô (obrigações + repasse do lote)."""
    return await AdvanceSettlementService(db).batch_history(batch_id)


@invoices_router.get(
    "/advance-repasse-ledger",
    response_model=RepasseLedgerStatementRead,
    dependencies=_read_view,
)
async def advance_repasse_ledger_statement(
    institution_id: UUID | None = Query(default=None),
    include_reversed: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
) -> RepasseLedgerStatementRead:
    ledger = AdvanceRepasseLedgerService(db)
    entries = await ledger.statement(institution_id=institution_id, include_reversed=include_reversed)
    if institution_id is not None:
        balance = float(await ledger.balance(institution_id))
    else:
        inst_ids = {e.institution_id for e in entries}
        total = Decimal("0.00")
        for i in inst_ids:
            total += await ledger.balance(i)
        balance = float(total)
    return RepasseLedgerStatementRead(
        institution_id=institution_id,
        balance=balance,
        entries=[RepasseLedgerEntryRead.model_validate(e) for e in entries],
    )


@invoices_router.post("", response_model=ReceivableInvoiceRead, dependencies=[Depends(require_permission(INVOICES_CREATE))])
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
    return await _invoice_read(svc, ReceivableAdvanceBatchService(db), loaded, prefix, actor)


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
    return await _invoice_read(svc, ReceivableAdvanceBatchService(db), loaded, prefix, actor)


@invoices_router.patch("/{invoice_id}", response_model=ReceivableInvoiceRead, dependencies=[Depends(require_permission(INVOICES_UPDATE))])
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
    return await _invoice_read(svc, ReceivableAdvanceBatchService(db), loaded, prefix, actor)


@invoices_router.delete("/{invoice_id}", status_code=204, dependencies=[Depends(require_permission(INVOICES_UPDATE))])
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


# Antecipações individuais da NF foram descontinuadas. A fonte oficial única
# passou a ser o módulo Antecipações (lotes/borderô). Os endpoints abaixo
# permanecem registrados apenas para responder 410 Gone de forma explícita;
# os registros legados continuam no banco somente para preservação histórica.
_ANTICIPATION_DISCONTINUED_MSG = (
    "Antecipações individuais foram descontinuadas. Toda criação, edição e "
    "cancelamento de antecipações deve ser realizada exclusivamente pelo módulo Antecipações."
)


@invoices_router.post(
    "/{invoice_id}/anticipations",
    dependencies=[Depends(require_permission(INVOICES_UPDATE))],
)
async def add_anticipation(invoice_id: UUID) -> None:
    raise HTTPException(status_code=410, detail=_ANTICIPATION_DISCONTINUED_MSG)


@invoices_router.delete(
    "/{invoice_id}/anticipations/{anticipation_id}",
    dependencies=[Depends(require_permission(INVOICES_UPDATE))],
)
async def delete_anticipation(invoice_id: UUID, anticipation_id: UUID) -> None:
    raise HTTPException(status_code=410, detail=_ANTICIPATION_DISCONTINUED_MSG)


@invoices_router.patch(
    "/{invoice_id}/anticipations/{anticipation_id}",
    dependencies=[Depends(require_permission(INVOICES_UPDATE))],
)
async def update_anticipation(invoice_id: UUID, anticipation_id: UUID) -> None:
    raise HTTPException(status_code=410, detail=_ANTICIPATION_DISCONTINUED_MSG)


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


@invoices_router.post("/{invoice_id}/pdf", dependencies=[Depends(require_permission(INVOICES_UPDATE))])
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
    return await _invoice_read(svc, ReceivableAdvanceBatchService(db), loaded, prefix, actor)


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


@invoices_router.delete("/{invoice_id}/pdf", response_model=ReceivableInvoiceRead, dependencies=[Depends(require_permission(INVOICES_UPDATE))])
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
    return await _invoice_read(svc, ReceivableAdvanceBatchService(db), loaded, prefix, actor)
