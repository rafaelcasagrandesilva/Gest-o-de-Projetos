from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import MissingGreenlet
from sqlalchemy import func, or_, select

from app.api.deps import (
    assert_may_write_scenario,
    default_scenario_for_create,
    ensure_project_access,
    get_accessible_project_ids,
    get_current_user,
    get_current_workspace,
    require_permission,
    user_has_permission,
    user_sees_all_projects,
)
from app.core.permission_codes import (
    BILLING_CREATE,
    BILLING_DELETE,
    BILLING_LIST,
    BILLING_READ,
    BILLING_UPDATE,
    FINANCIAL_DASHBOARD_READ,
    INVOICES_REACTIVATE,
    INVOICES_CREATE,
    INVOICES_LIST,
    INVOICES_UPDATE,
    PAYABLES_LIST,
    PAYABLES_UPDATE,
    PAYABLE_SNAPSHOT_RECONCILE,
    RECEIVABLES_CREATE,
    RECEIVABLES_DELETE,
    RECEIVABLES_LIST,
    RECEIVABLES_UPDATE,
)
from app.core.scenario import coerce_scenario, parse_scenario
from app.database.session import get_db
from app.api.sensitive import redact_for
from app.models.user import User
from app.schemas.financial import (
    InvoiceAnticipationCreate,
    InvoiceAnticipationRead,
    InvoiceCreate,
    InvoiceRead,
    RevenueCreate,
    RevenueRead,
    RevenueUpdate,
)
from app.models.payable_snapshot import PayableSnapshotType, default_origin_for_type
from app.schemas.cost_center_alias import CostCenterAliasCreate, CostCenterAliasRead
from app.schemas.payable_import import (
    PayableImportAnalyzeResult,
    PayableImportConfirmResult,
    PayableImportCostCenterScanResult,
    PayableImportPreviewResult,
    PayableImportTemplateCreate,
    PayableImportTemplateRead,
)
from app.services.cost_center_alias_service import CostCenterAliasService
from app.schemas.payables import (
    PayableSnapshotManualCreate,
    PayableSnapshotReconcileResult,
    PayableSnapshotRegisterPaymentBody,
    PayableSnapshotReversePaymentBody,
    PayableSnapshotRead,
    PayableSnapshotUpdate,
)
from app.services.payable_import import MAX_IMPORT_BYTES, PayableManualImportService
from app.services.invoice_billing import billed_totals_by_competencia
from app.services.financial_crud_service import FinancialCrudService
from app.services.company_finance_service import CompanyFinanceService
from app.services.finance_service import FinanceService
from app.services.payable_snapshot_service import PAYABLE_DEBT_TYPES, payable_snapshot_derived_fields
from app.services.receivable_service import ReceivableService
from app.services.receivable_manual_service import ReceivableManualService
from app.utils.date_utils import normalize_competencia, previous_competencia
from app.repositories.projects import ProjectRepository
from app.schemas.receivable import (
    ReceivableManualItemCreate,
    ReceivableManualItemRead,
    ReceivableManualItemUpdate,
    ReceivableViewRead,
)
from app.models.receivable_advance_batch import (
    ReceivableAdvanceBatch,
    ReceivableAdvanceBatchItem,
    ReceivableAdvanceBatchStatus,
)
from app.models.receivable import ReceivableInvoice
from app.schemas.financial_dashboard import (
    FinancialDashboardBreakdownRead,
    FinancialDashboardGroupedItem,
    FinancialDashboardRead,
    FinancialDashboardSummaryRead,
    FinancialDashboardTimeseriesPoint,
)
from app.services.financial_dashboard_service import FinancialDashboardService


_read = [Depends(require_permission(BILLING_LIST))]

router = APIRouter()


def _receivable_view_status(*, net_value: float, total_received: float) -> str:
    net = float(net_value or 0.0)
    recv = float(total_received or 0.0)
    if recv <= 0:
        return "ABERTO"
    if recv + 0.01 < net:
        return "PARCIAL"
    return "RECEBIDO"


@router.get("/receivables", response_model=list[ReceivableViewRead], dependencies=[Depends(require_permission(RECEIVABLES_LIST))])
async def list_receivables_view(
    request: Request,
    project_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(EMITIDA|ANTECIPADA|RECEBIDA|CANCELADA)$"),
    client: str | None = Query(default=None, max_length=255),
    tipo: str | None = Query(default=None, pattern="^(NF|MANUAL|ANTECIPACAO|BORDERO)$"),
    period_field: str = Query(default="issue", pattern="^(issue|due)$"),
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _ws: str = Depends(get_current_workspace),
) -> list[ReceivableViewRead]:
    if (year is None) != (month is None):
        raise HTTPException(status_code=400, detail="Informe ano e mês juntos para o período, ou deixe ambos vazios.")

    sees_all = user_sees_all_projects(user)
    allowed = None if sees_all else await get_accessible_project_ids(user, db)

    out: list[ReceivableViewRead] = []
    can_see_cancelled = user_has_permission(user, INVOICES_REACTIVATE)
    if tipo is None or tipo == "NF":
        svc = ReceivableService(db)
        rows = await svc.list_invoices(
            project_id=project_id if project_id is not None else None,
            project_ids=None if (project_id is not None or sees_all) else allowed,
            status=status,
            client_busca=client,
            year=year,
            month=month,
            period_field=period_field,
        )
        for inv in rows:
            inv_status = (inv.invoice_status or "").upper()
            if inv_status == "CANCELADA":
                if not can_see_cancelled:
                    continue
            # NF liquidada por uma operação de antecipação (ex.: Daycoval): quem recebeu foi
            # o banco, não o cliente. A receita já é representada pela linha da própria
            # operação (tipo BORDERO). A NF permanece como documento fiscal/histórico
            # operacional (módulo de NFs), mas não gera linha financeira própria aqui —
            # evitando dupla contagem da receita. Sinal: vinculada a um lote E RECEBIDA
            # (LEPTA fica ANTECIPADA; recebimento normal do cliente não tem advance_batch_id).
            if getattr(inv, "advance_batch_id", None) is not None and inv_status == "RECEBIDA":
                continue
            net = float(inv.net_amount or 0.0)
            recv_customer = float(inv.received_amount or 0.0)
            try:
                ants = list(getattr(inv, "anticipations", []) or [])
            except MissingGreenlet:
                ants = []
            recv_advance = (
                float(sum(float(a.amount_received or 0.0) for a in ants)) if ants else float(inv.advance_amount_received or 0.0)
            )
            total_recv = round(recv_customer + recv_advance, 2)
            remaining = round(max(0.0, net - total_recv), 2)
            out.append(
                ReceivableViewRead(
                    id=inv.id,
                    created_at=inv.created_at,
                    updated_at=inv.updated_at,
                    tipo="NF",
                    client=inv.client_name,
                    number=inv.nf_number,
                    issue_date=inv.issue_date,
                    due_date=inv.due_date,
                    received_at=inv.received_date,
                    net_value=net,
                    amount_received_advance=round(recv_advance, 2),
                    amount_received_customer=round(recv_customer, 2),
                    total_received=total_recv,
                    remaining=remaining,
                    status=_receivable_view_status(net_value=net, total_received=total_recv),  # type: ignore[arg-type]
                    invoice_status=inv_status if inv_status == "CANCELADA" else None,
                    include_in_dashboard=bool(getattr(inv, "include_in_dashboard", True)),
                )
            )

    if tipo is None or tipo == "MANUAL":
        manual_svc = ReceivableManualService(db)
        manual_rows = await manual_svc.list(
            workspace_id=request.state.workspace,
            client=client,
            year=year,
            month=month,
            period_field=period_field,
        )
        for it in manual_rows:
            net = float(it.valor_liquido or 0.0)
            recv = float(it.valor_recebido or 0.0)
            total_recv = round(recv, 2)
            remaining = round(max(0.0, net - total_recv), 2)
            out.append(
                ReceivableViewRead(
                    id=it.id,
                    created_at=it.created_at,
                    updated_at=it.updated_at,
                    tipo="MANUAL",
                    client=it.cliente,
                    number=(it.numero_referencia or "-"),
                    descricao=it.descricao,
                    numero_referencia=it.numero_referencia,
                    issue_date=it.data_emissao,
                    due_date=it.data_vencimento,
                    received_at=it.data_recebimento,
                    net_value=round(net, 2),
                    amount_received_advance=0.0,
                    amount_received_customer=round(recv, 2),
                    total_received=total_recv,
                    remaining=remaining,
                    status=str(it.status.value if hasattr(it.status, "value") else it.status),
                    observacao=it.observacao,
                    include_in_dashboard=bool(getattr(it, "include_in_dashboard", True)),
                )
            )

    if tipo is None or tipo == "ANTECIPACAO":
        # Antecipações como entrada de caixa (linha separada) — mês sempre pelo recebimento.
        svc = ReceivableService(db)
        invs = await svc.list_invoices(
            project_id=project_id if project_id is not None else None,
            project_ids=None if (project_id is not None or sees_all) else allowed,
            status=None,
            client_busca=client,
            year=None,
            month=None,
            period_field="issue",
        )
        start = end = None
        if year is not None and month is not None:
            start, end = date(year, month, 1), date(year, month, 28)
            # último dia real do mês
            import calendar

            last = calendar.monthrange(year, month)[1]
            end = date(year, month, last)

        for inv in invs:
            try:
                ants = list(getattr(inv, "anticipations", []) or [])
            except MissingGreenlet:
                ants = []
            for a in ants:
                rd = getattr(a, "received_date", None)
                if rd is None:
                    continue
                if start and end and not (start <= rd <= end):
                    continue
                val = float(a.amount_received or 0.0)
                if val <= 0:
                    continue
                out.append(
                    ReceivableViewRead(
                        id=a.id,
                        created_at=a.created_at,
                        updated_at=a.updated_at,
                        tipo="ANTECIPACAO",
                        client=inv.client_name,
                        number=inv.nf_number,
                        descricao=f"Antecipação - NF {inv.nf_number}",
                        issue_date=rd,
                        due_date=rd,
                        received_at=rd,
                        net_value=round(val, 2),
                        amount_received_advance=round(val, 2),
                        amount_received_customer=0.0,
                        total_received=round(val, 2),
                        remaining=0.0,
                        status="RECEBIDO",
                        include_in_dashboard=bool(getattr(a, "include_in_dashboard", True)),
                    )
                )

    if tipo is None or tipo == "BORDERO":
        # Borderôs como evento de recebimento (linha separada) — mês sempre pelo receive_date.
        start = end = None
        if year is not None and month is not None:
            start, end = date(year, month, 1), date(year, month, 28)
            import calendar

            last = calendar.monthrange(year, month)[1]
            end = date(year, month, last)

        stmt = (
            select(ReceivableAdvanceBatch)
            .where(
                ReceivableAdvanceBatch.status.notin_(
                    [ReceivableAdvanceBatchStatus.CANCELLED, ReceivableAdvanceBatchStatus.DRAFT]
                )
            )
            .order_by(ReceivableAdvanceBatch.receive_date.desc(), ReceivableAdvanceBatch.batch_number.desc())
        )
        if start and end:
            stmt = stmt.where(
                ReceivableAdvanceBatch.receive_date >= start,
                ReceivableAdvanceBatch.receive_date <= end,
            )
        q = (client or "").strip().lower()
        if q:
            stmt = stmt.where(func.lower(ReceivableAdvanceBatch.institution).contains(q))

        # Escopo por projeto/permissões: borderô aparece se tiver ao menos 1 NF elegível no escopo.
        # Usa a tabela de junção (relacionamento N:N) em vez do ponteiro escalar
        # advance_batch_id — que, com múltiplas operações por NF, deixa de ser confiável.
        if project_id is not None or (not sees_all and allowed is not None):
            stmt = stmt.join(
                ReceivableAdvanceBatchItem,
                ReceivableAdvanceBatchItem.batch_id == ReceivableAdvanceBatch.id,
            ).join(
                ReceivableInvoice,
                ReceivableInvoice.id == ReceivableAdvanceBatchItem.invoice_id,
            )
            if project_id is not None:
                stmt = stmt.where(ReceivableInvoice.project_id == project_id)
            elif allowed is not None:
                stmt = stmt.where(ReceivableInvoice.project_id.in_(allowed))
            stmt = stmt.distinct()

        rows = list((await db.execute(stmt)).scalars().unique().all())
        for b in rows:
            rd = b.receive_date
            # Linha derivada da operação (não persistida como receita independente).
            # Uma operação de antecipação é um EVENTO DE CAIXA CONCLUÍDO: nunca há saldo a
            # receber. A diferença previsto×realizado é custo financeiro da operação
            # (juros/desconto/tarifas do banco), NÃO dinheiro a receber. Por isso a linha
            # usa sempre o valor efetivamente recebido (received_amount) como líquido e
            # recebido, com saldo zero e status RECEBIDO — independentemente do previsto.
            realizado = float(b.received_amount or 0.0)
            previsto = float(b.expected_amount if b.expected_amount is not None else realizado)
            if previsto <= 0 and realizado <= 0:
                continue
            out.append(
                ReceivableViewRead(
                    id=b.id,
                    created_at=b.created_at,
                    updated_at=b.updated_at,
                    tipo="BORDERO",
                    client=b.institution,
                    # NF / Referência padronizado para o número interno do SGC (localização
                    # rápida no menu Antecipações). O número da instituição (operation_code)
                    # permanece no detalhe da operação e na tela de Antecipações.
                    number=f"SGC {b.sgc_number}",
                    descricao=f"Antecipação de NF — {b.institution}",
                    numero_referencia=f"SGC {b.sgc_number}",
                    issue_date=rd,
                    due_date=rd,
                    received_at=rd,
                    net_value=round(realizado, 2),
                    amount_received_advance=round(realizado, 2),
                    amount_received_customer=0.0,
                    total_received=round(realizado, 2),
                    remaining=0.0,
                    status="RECEBIDO",
                    observacao=b.observation,
                    include_in_dashboard=bool(getattr(b, "include_in_dashboard", True)),
                )
            )
    return [redact_for("receivables", m, user) for m in out]


@router.post(
    "/receivables/manual",
    response_model=ReceivableManualItemRead,
    dependencies=[Depends(require_permission(RECEIVABLES_CREATE))],
)
async def create_receivable_manual_item(
    payload: ReceivableManualItemCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _ws: str = Depends(get_current_workspace),
) -> ReceivableManualItemRead:
    svc = ReceivableManualService(db)
    data = payload.model_dump()
    try:
        row = await svc.create(workspace_id=request.state.workspace, data=data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return redact_for("receivables_manual", ReceivableManualItemRead.model_validate(row, from_attributes=True), user)


@router.patch(
    "/receivables/manual/{item_id}",
    response_model=ReceivableManualItemRead,
    dependencies=[Depends(require_permission(RECEIVABLES_UPDATE))],
)
async def update_receivable_manual_item(
    item_id: UUID,
    payload: ReceivableManualItemUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _ws: str = Depends(get_current_workspace),
) -> ReceivableManualItemRead:
    svc = ReceivableManualService(db)
    data = payload.model_dump(exclude_unset=True)
    try:
        row = await svc.update(item_id=item_id, data=data)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if row.workspace_id != request.state.workspace:
        raise HTTPException(status_code=404, detail="Receita manual não encontrada.")
    return redact_for("receivables_manual", ReceivableManualItemRead.model_validate(row, from_attributes=True), user)


@router.delete(
    "/receivables/manual/{item_id}",
    status_code=204,
    dependencies=[Depends(require_permission(RECEIVABLES_DELETE))],
)
async def delete_receivable_manual_item(
    item_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _ws: str = Depends(get_current_workspace),
) -> None:
    svc = ReceivableManualService(db)
    row = await svc.get(item_id)
    if not row or row.workspace_id != request.state.workspace:
        raise HTTPException(status_code=404, detail="Receita manual não encontrada.")
    await svc.delete(item_id=item_id)


@router.get("/revenues", response_model=list[RevenueRead], dependencies=_read)
async def list_revenues(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    project_id: UUID | None = Query(default=None),
    scenario_param: str | None = Query(default=None, alias="scenario", description="Omitir = REALIZADO"),
) -> list[RevenueRead]:
    sc = coerce_scenario(scenario_param)
    svc = FinancialCrudService(db)
    if not user_sees_all_projects(user):
        allowed = await get_accessible_project_ids(user, db)
        if project_id is not None:
            if project_id not in allowed:
                raise HTTPException(status_code=403, detail="Sem permissão.")
            rows = await svc.list_revenues(
                offset=offset, limit=limit, project_id=project_id, scenario=sc
            )
        else:
            rows = await svc.list_revenues(
                offset=offset, limit=limit, project_ids=allowed, scenario=sc
            )
    else:
        rows = await svc.list_revenues(offset=offset, limit=limit, project_id=project_id, scenario=sc)

    # Conciliação: a soma faturada de cada (projeto, competência) numa consulta agrupada só,
    # e não uma por linha. A redação de Dados sensíveis vem DEPOIS de preencher `nf_amount`,
    # para que ele seja ocultado junto com `amount` (ambos em REVENUE_SENSITIVE_FIELDS).
    billed = await billed_totals_by_competencia(
        db,
        project_ids=list({r.project_id for r in rows}),
        competencias=list({r.competencia for r in rows}),
    )
    out: list[RevenueRead] = []
    for r in rows:
        item = RevenueRead.model_validate(r)
        item.nf_amount = billed.get((r.project_id, r.competencia))
        out.append(redact_for("billing_revenue", item, user))
    return out


@router.post("/revenues", response_model=RevenueRead, dependencies=[Depends(require_permission(BILLING_CREATE))])
async def create_revenue(
    payload: RevenueCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> RevenueRead:
    await ensure_project_access(user=actor, project_id=payload.project_id, db=db)
    data = payload.model_dump()
    sc = parse_scenario(data.get("scenario"), default=default_scenario_for_create(actor))
    await assert_may_write_scenario(
        user=actor, scenario=sc, db=db, project_id=payload.project_id
    )
    data["scenario"] = sc
    row = await FinancialCrudService(db).create_revenue(
        actor_user_id=actor.id, data=data, actor=actor, request=request
    )
    return redact_for("billing_revenue", RevenueRead.model_validate(row), actor)


@router.patch("/revenues/{revenue_id}", response_model=RevenueRead, dependencies=[Depends(require_permission(BILLING_UPDATE))])
async def update_revenue(
    revenue_id: UUID,
    payload: RevenueUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> RevenueRead:
    svc = FinancialCrudService(db)
    row = await svc.revenues.get(revenue_id)
    if not row:
        raise HTTPException(status_code=404, detail="Receita não encontrada.")
    await ensure_project_access(user=actor, project_id=row.project_id, db=db)
    await assert_may_write_scenario(
        user=actor, scenario=row.scenario, db=db, project_id=row.project_id
    )
    row = await svc.update_revenue(
        actor_user_id=actor.id,
        revenue_id=revenue_id,
        data=payload.model_dump(exclude_unset=True),
        actor=actor,
        request=request,
    )
    return redact_for("billing_revenue", RevenueRead.model_validate(row), actor)


@router.delete("/revenues/{revenue_id}", status_code=204, dependencies=[Depends(require_permission(BILLING_DELETE))])
async def delete_revenue(
    revenue_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> None:
    svc = FinancialCrudService(db)
    row = await svc.revenues.get(revenue_id)
    if not row:
        raise HTTPException(status_code=404, detail="Receita não encontrada.")
    await ensure_project_access(user=actor, project_id=row.project_id, db=db)
    await assert_may_write_scenario(
        user=actor, scenario=row.scenario, db=db, project_id=row.project_id
    )
    await svc.delete_revenue(actor_user_id=actor.id, revenue_id=revenue_id, actor=actor, request=request)


@router.get("/invoices", response_model=list[InvoiceRead], dependencies=[Depends(require_permission(INVOICES_LIST))])
async def list_invoices(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    project_id: UUID | None = Query(default=None),
) -> list[InvoiceRead]:
    svc = FinancialCrudService(db)
    if not user_sees_all_projects(user):
        allowed = await get_accessible_project_ids(user, db)
        if project_id is not None:
            if project_id not in allowed:
                raise HTTPException(status_code=403, detail="Sem permissão.")
            rows = await svc.list_invoices(offset=offset, limit=limit, project_id=project_id)
        else:
            rows = await svc.list_invoices(offset=offset, limit=limit, project_ids=allowed)
    else:
        rows = await svc.list_invoices(offset=offset, limit=limit, project_id=project_id)
    return [redact_for("billing_invoice", InvoiceRead.model_validate(r), user) for r in rows]


@router.post("/invoices", response_model=InvoiceRead, dependencies=[Depends(require_permission(INVOICES_CREATE))])
async def create_invoice(
    payload: InvoiceCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> InvoiceRead:
    await ensure_project_access(user=actor, project_id=payload.project_id, db=db)
    row = await FinancialCrudService(db).create_invoice(
        actor_user_id=actor.id, data=payload.model_dump(), actor=actor, request=request
    )
    return redact_for("billing_invoice", InvoiceRead.model_validate(row), actor)


@router.post("/invoices/anticipations", response_model=InvoiceAnticipationRead, dependencies=[Depends(require_permission(INVOICES_UPDATE))])
async def create_anticipation(
    payload: InvoiceAnticipationCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> InvoiceAnticipationRead:
    svc = FinancialCrudService(db)
    inv = await svc.invoices.get(payload.invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Nota fiscal não encontrada.")
    await ensure_project_access(user=actor, project_id=inv.project_id, db=db)
    row = await svc.create_anticipation(
        actor_user_id=actor.id, data=payload.model_dump(), actor=actor, request=request
    )
    return redact_for("billing_invoice_anticipation", InvoiceAnticipationRead.model_validate(row), actor)


def _parse_month(value: str) -> date:
    try:
        y, m = value.split("-", 1)
        year = int(y)
        month = int(m)
        return normalize_competencia(date(year, month, 1))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Parâmetro month inválido. Use YYYY-MM.") from e


@router.get(
    "/dashboard",
    response_model=FinancialDashboardRead,
    dependencies=[Depends(require_permission(FINANCIAL_DASHBOARD_READ))],
)
async def financial_dashboard(
    month: str = Query(..., description="Mês âncora (YYYY-MM)."),
    months: int = Query(default=1, ge=1, le=24, description="Período (em meses)."),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    workspace: str = Depends(get_current_workspace),
) -> FinancialDashboardRead:
    comp = _parse_month(month)
    svc = FinancialDashboardService(db)
    summary, points = await svc.cash_summary_and_series(month=comp, months=months, workspace_id=workspace)
    await db.commit()
    # Dados sensíveis: sem `financial_dashboard.sensitive`, os valores (faturamento/pago/caixa) saem None.
    return redact_for("financial_dashboard", FinancialDashboardRead(
        summary=FinancialDashboardSummaryRead(
            month=summary.month,
            period_start=summary.period_start,
            period_end=summary.period_end,
            faturamento=summary.faturamento,
            pago=summary.pago,
            caixa=summary.caixa,
        ),
        timeseries=[
            FinancialDashboardTimeseriesPoint(
                month=p.month,
                faturamento=p.faturamento,
                pago=p.pago,
                caixa=p.caixa,
            )
            for p in points
        ],
    ), user)


@router.get(
    "/dashboard/timeseries",
    response_model=list[FinancialDashboardTimeseriesPoint],
    dependencies=[Depends(require_permission(FINANCIAL_DASHBOARD_READ))],
)
async def financial_dashboard_timeseries(
    month: str = Query(..., description="Mês âncora (YYYY-MM)."),
    months: int = Query(default=12, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    workspace: str = Depends(get_current_workspace),
) -> list[FinancialDashboardTimeseriesPoint]:
    comp = _parse_month(month)
    svc = FinancialDashboardService(db)
    _, points = await svc.cash_summary_and_series(month=comp, months=months, workspace_id=workspace)
    await db.commit()
    return [
        redact_for("financial_dashboard_point", FinancialDashboardTimeseriesPoint(
            month=p.month,
            faturamento=p.faturamento,
            pago=p.pago,
            caixa=p.caixa,
        ), user)
        for p in points
    ]


@router.get(
    "/dashboard/breakdown",
    response_model=FinancialDashboardBreakdownRead,
    dependencies=[Depends(require_permission(FINANCIAL_DASHBOARD_READ))],
)
async def financial_dashboard_breakdown(
    type: str = Query(..., pattern="^(faturamento|custos|caixa)$"),
    month: str = Query(..., description="Mês (YYYY-MM)."),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    workspace: str = Depends(get_current_workspace),
) -> FinancialDashboardBreakdownRead:
    comp = _parse_month(month)
    svc = FinancialDashboardService(db)
    total, groups, received_total, received_groups, paid_total, paid_groups = await svc.cash_breakdown(
        type=type, month=comp, workspace_id=workspace
    )
    await db.commit()
    return redact_for("financial_dashboard_breakdown", FinancialDashboardBreakdownRead(
        type=type,  # type: ignore[arg-type]
        month=comp,
        total=total,
        groups=[FinancialDashboardGroupedItem(label=g.label, value=g.valor) for g in groups],
        received_total=received_total,
        received_groups=(
            [FinancialDashboardGroupedItem(label=g.label, value=g.valor) for g in (received_groups or [])]
            if received_groups is not None
            else None
        ),
        paid_total=paid_total,
        paid_groups=(
            [FinancialDashboardGroupedItem(label=g.label, value=g.valor) for g in (paid_groups or [])]
            if paid_groups is not None
            else None
        ),
    ), user)


def _snapshot_to_read(
    row,
    *,
    last_payment_date: date | None = None,
    paid_in_period: float = 0.0,
    view_month: date | None = None,
) -> PayableSnapshotRead:
    amount_final = float(row.amount_final)
    amount_paid = float(row.amount_paid or 0)
    derived = payable_snapshot_derived_fields(
        amount_paid=Decimal(str(amount_paid)),
        amount_final=Decimal(str(amount_final)),
    )
    st = derived["status"]
    competence_out_of_view = False
    if view_month is not None:
        competence_out_of_view = normalize_competencia(row.month) != normalize_competencia(view_month)
    return PayableSnapshotRead(
        id=row.id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        month=row.month,
        type="ENDIVIDAMENTO" if row.type == PayableSnapshotType.FINANCIAL else row.type.value,
        ref_id=row.ref_id,
        project_id=row.project_id,
        name=row.name,
        item_description=getattr(row, "item_description", None),
        cost_center=row.cost_center,
        category=row.category,
        origin=getattr(row, "origin", None) or default_origin_for_type(row.type),
        amount_original=float(row.amount_original),
        amount_final=amount_final,
        amount_paid=amount_paid,
        amount_remaining=float(derived["amount_remaining"]),
        is_overpaid=bool(derived["is_overpaid"]),
        overpaid_amount=float(derived["overpaid_amount"]),
        due_date=row.due_date,
        payment_date=row.payment_date,
        paid=st == "PAGO",
        observation=row.observation,
        include_in_dashboard=bool(getattr(row, "include_in_dashboard", True)),
        is_obsolete=bool(getattr(row, "is_obsolete", False)),
        obsolete_reason=getattr(row, "obsolete_reason", None),
        reconciled_at=getattr(row, "reconciled_at", None),
        status=st,
        last_payment_date=last_payment_date,
        paid_in_period=paid_in_period,
        competence_out_of_view=competence_out_of_view,
    )


async def _snapshots_to_read(
    svc, rows: list, *, view_month: date | None = None, user: User | None = None
) -> list[PayableSnapshotRead]:
    if not rows:
        return []
    ids = [r.id for r in rows]
    dates = await svc.last_payment_dates_by_snapshot_ids(ids)
    paid_map: dict = {}
    if view_month is not None:
        paid_map = await svc.paid_in_period_by_snapshot_ids(ids, month=view_month)
    reads = [
        _snapshot_to_read(
            r,
            last_payment_date=dates.get(r.id),
            paid_in_period=float(paid_map.get(r.id, 0)),
            view_month=view_month,
        )
        for r in rows
    ]
    # Dados sensíveis: sem `payables.sensitive`, o backend omite os valores (envia None).
    if user is not None:
        reads = [redact_for("payables", m, user) for m in reads]
    return reads


@router.get("/payables", response_model=list[PayableSnapshotRead], dependencies=[Depends(require_permission(PAYABLES_LIST))])
async def list_payables_snapshot(
    month: str | None = Query(
        default=None,
        description="Mês operacional (YYYY-MM): em aberto na competência + pagamentos realizados no mês. Omitir = todos.",
    ),
    force_regenerate: bool = Query(default=False, description="Regerar snapshot do mês (apaga snapshot existente)."),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PayableSnapshotRead]:
    if force_regenerate and not user_has_permission(user, PAYABLE_SNAPSHOT_RECONCILE):
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para regerar o snapshot de contas a pagar (payable_snapshot.reconcile).",
        )
    sees_all = user_sees_all_projects(user)
    allowed = None if sees_all else set(await get_accessible_project_ids(user, db))
    if not sees_all and (not allowed):
        # Financeiro ignora escopo de project_users: fallback para todos projetos.
        all_ids = await ProjectRepository(db).list_all_project_ids()
        allowed = set(all_ids)

    # month omitido: retorna todos os snapshots já salvos (não gera em massa).
    if month is None or (isinstance(month, str) and not month.strip()):
        svc = FinanceService(db).payable_snapshots
        rows = await svc.list_all()
        await db.commit()
        return await _snapshots_to_read(svc, rows, user=user)

    comp = _parse_month(month)

    try:
        await FinanceService(db).get_or_create_payables_snapshot(
            month=comp,
            accessible_project_ids=allowed,
            sees_all_projects=sees_all,
            force_regenerate=force_regenerate,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        # Temporário: expõe contexto para diagnóstico de 500.
        raise HTTPException(
            status_code=500,
            detail={
                "message": str(e),
                "month": comp.isoformat(),
                "source_month": previous_competencia(comp).isoformat(),
                "sees_all_projects": sees_all,
                "accessible_project_count": 0 if not allowed else len(allowed),
                "force_regenerate": force_regenerate,
            },
        ) from e

    await db.commit()
    svc = FinanceService(db).payable_snapshots
    operational_rows = await svc.list_for_operational_month(month=comp)
    if not sees_all and allowed is not None:
        op_filtered: list = []
        for r in operational_rows:
            if r.type in (
                PayableSnapshotType.VEHICLE,
                PayableSnapshotType.FIXED_COST,
                PayableSnapshotType.ENDIVIDAMENTO,
                PayableSnapshotType.FINANCIAL,
                PayableSnapshotType.MANUAL,
                PayableSnapshotType.ANTECIPACAO,
                PayableSnapshotType.ANTECIPACAO_OPERACAO,
            ):
                op_filtered.append(r)
                continue
            if r.type == PayableSnapshotType.COLLABORATOR and r.project_id in allowed:
                op_filtered.append(r)
        operational_rows = op_filtered
    return await _snapshots_to_read(svc, operational_rows, view_month=comp, user=user)


async def _ensure_payable_snapshot_edit_access(*, row, user: User, db: AsyncSession) -> None:
    if not user_sees_all_projects(user):
        allowed = set(await get_accessible_project_ids(user, db))
        if not allowed:
            allowed = set(await ProjectRepository(db).list_all_project_ids())
        if row.type == PayableSnapshotType.COLLABORATOR and row.project_id not in allowed:
            raise HTTPException(status_code=403, detail="Sem permissão.")


@router.patch("/payables/{snapshot_id}", response_model=PayableSnapshotRead, dependencies=[Depends(require_permission(PAYABLES_UPDATE))])
async def update_payables_snapshot(
    snapshot_id: UUID,
    payload: PayableSnapshotUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PayableSnapshotRead:
    svc = FinanceService(db).payable_snapshots
    row = await svc.get(snapshot_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    await _ensure_payable_snapshot_edit_access(row=row, user=user, db=db)

    data = payload.model_dump(exclude_unset=True)
    updated = await svc.update_row(
        row=row,
        amount_final=data.get("amount_final"),
        due_date=data.get("due_date"),
        observation=data.get("observation"),
        include_in_dashboard=data.get("include_in_dashboard"),
    )
    await db.commit()
    dates = await FinanceService(db).payable_snapshots.last_payment_dates_by_snapshot_ids([updated.id])
    return redact_for("payables", _snapshot_to_read(updated, last_payment_date=dates.get(updated.id)), user)


@router.post(
    "/payables/{snapshot_id}/register-payment",
    response_model=PayableSnapshotRead,
    dependencies=[Depends(require_permission(PAYABLES_UPDATE))],
)
async def register_payables_payment(
    snapshot_id: UUID,
    payload: PayableSnapshotRegisterPaymentBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PayableSnapshotRead:
    svc = FinanceService(db).payable_snapshots
    row = await svc.get(snapshot_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    await _ensure_payable_snapshot_edit_access(row=row, user=user, db=db)
    try:
        updated = await svc.register_payment(
            row=row,
            amount=payload.amount,
            payment_date=payload.payment_date,
            observation=payload.observation,
            created_by=user.id,
            allow_overpayment=payload.allow_overpayment,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    # Foi a última parcela? Cronograma quitado inativa o cadastro, com encerramento no mês
    # SEGUINTE — o item segue visível (e a competência atual intacta) até a virada.
    if updated.type in PAYABLE_DEBT_TYPES and updated.ref_id is not None:
        await CompanyFinanceService(db).auto_close_settled_schedule(item_id=updated.ref_id)
    await db.commit()
    dates = await svc.last_payment_dates_by_snapshot_ids([updated.id])
    return redact_for("payables", _snapshot_to_read(updated, last_payment_date=dates.get(updated.id)), user)


@router.post(
    "/payables/{snapshot_id}/reverse-payment",
    response_model=PayableSnapshotRead,
    dependencies=[Depends(require_permission(PAYABLES_UPDATE))],
)
async def reverse_payables_payment(
    snapshot_id: UUID,
    payload: PayableSnapshotReversePaymentBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PayableSnapshotRead:
    svc = FinanceService(db).payable_snapshots
    row = await svc.get(snapshot_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    await _ensure_payable_snapshot_edit_access(row=row, user=user, db=db)
    try:
        updated = await svc.reverse_payment(
            row=row,
            amount=payload.amount,
            observation=payload.observation,
            reversal_reason=payload.reversal_reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await db.commit()
    dates = await svc.last_payment_dates_by_snapshot_ids([updated.id])
    return redact_for("payables", _snapshot_to_read(updated, last_payment_date=dates.get(updated.id)), user)


async def _read_payables_import_file(file: UploadFile) -> tuple[bytes, str]:
    name = (file.filename or "").lower()
    if not (name.endswith(".xlsx") or name.endswith(".csv")):
        raise HTTPException(status_code=400, detail="Envie um arquivo .xlsx ou .csv.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="Arquivo muito grande (máximo 5 MB).")
    return content, name


@router.post(
    "/payables/import/analyze",
    response_model=PayableImportAnalyzeResult,
    dependencies=[Depends(require_permission(PAYABLES_UPDATE))],
)
async def analyze_payables_import(
    file: UploadFile = File(...),
    header_row: int = Form(1),
    db: AsyncSession = Depends(get_db),
) -> PayableImportAnalyzeResult:
    content, filename = await _read_payables_import_file(file)
    try:
        return await PayableManualImportService(db).analyze(
            content, filename=filename, header_row=header_row
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/payables/import/mapped/scan-cost-centers",
    response_model=PayableImportCostCenterScanResult,
    dependencies=[Depends(require_permission(PAYABLES_UPDATE))],
)
async def scan_payables_import_cost_centers(
    file: UploadFile = File(...),
    header_row: int = Form(1),
    mapping: str = Form(..., description="JSON com mapeamento de colunas"),
    db: AsyncSession = Depends(get_db),
) -> PayableImportCostCenterScanResult:
    content, filename = await _read_payables_import_file(file)
    svc = PayableManualImportService(db)
    try:
        col_map = svc.parse_mapping_json(mapping)
        return await svc.scan_mapped_cost_centers(
            content, filename=filename, header_row=header_row, mapping=col_map
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/payables/import/mapped/preview",
    response_model=PayableImportPreviewResult,
    dependencies=[Depends(require_permission(PAYABLES_UPDATE))],
)
async def preview_payables_import_mapped(
    file: UploadFile = File(...),
    header_row: int = Form(1),
    mapping: str = Form(..., description="JSON com mapeamento de colunas"),
    cost_center_resolutions: str | None = Form(
        None, description="JSON mapa texto planilha → centro de custo SGP"
    ),
    db: AsyncSession = Depends(get_db),
) -> PayableImportPreviewResult:
    content, filename = await _read_payables_import_file(file)
    svc = PayableManualImportService(db)
    try:
        col_map = svc.parse_mapping_json(mapping)
        resolutions = svc.parse_cost_center_resolutions_json(cost_center_resolutions)
        return await svc.preview_mapped(
            content,
            filename=filename,
            header_row=header_row,
            mapping=col_map,
            cost_center_resolutions=resolutions or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/payables/import/mapped/confirm",
    response_model=PayableImportConfirmResult,
    dependencies=[Depends(require_permission(PAYABLES_UPDATE))],
)
async def confirm_payables_import_mapped(
    file: UploadFile = File(...),
    header_row: int = Form(1),
    mapping: str = Form(..., description="JSON com mapeamento de colunas"),
    cost_center_resolutions: str | None = Form(
        None, description="JSON mapa texto planilha → centro de custo SGP"
    ),
    db: AsyncSession = Depends(get_db),
) -> PayableImportConfirmResult:
    content, filename = await _read_payables_import_file(file)
    svc = PayableManualImportService(db)
    try:
        col_map = svc.parse_mapping_json(mapping)
        resolutions = svc.parse_cost_center_resolutions_json(cost_center_resolutions)
        result = await svc.confirm_mapped(
            content,
            filename=filename,
            header_row=header_row,
            mapping=col_map,
            cost_center_resolutions=resolutions or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return result


@router.get(
    "/cost-center-aliases",
    response_model=list[CostCenterAliasRead],
    dependencies=[Depends(require_permission(PAYABLES_UPDATE))],
)
async def list_cost_center_aliases(
    db: AsyncSession = Depends(get_db),
) -> list[CostCenterAliasRead]:
    rows = await CostCenterAliasService(db).list_aliases()
    return [
        CostCenterAliasRead(
            id=r.id,
            alias_name=r.alias_name,
            target_cost_center=r.target_cost_center,
            created_by_user_id=r.created_by_user_id,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post(
    "/cost-center-aliases",
    response_model=CostCenterAliasRead,
    dependencies=[Depends(require_permission(PAYABLES_UPDATE))],
)
async def create_cost_center_alias(
    payload: CostCenterAliasCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CostCenterAliasRead:
    try:
        row = await CostCenterAliasService(db).create_alias(
            alias_name=payload.alias_name,
            target_cost_center=payload.target_cost_center,
            created_by_user_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return CostCenterAliasRead(
        id=row.id,
        alias_name=row.alias_name,
        target_cost_center=row.target_cost_center,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
    )


@router.delete(
    "/cost-center-aliases/{alias_id}",
    status_code=204,
    dependencies=[Depends(require_permission(PAYABLES_UPDATE))],
)
async def delete_cost_center_alias(
    alias_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    ok = await CostCenterAliasService(db).delete_alias(alias_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Alias não encontrado.")
    await db.commit()


@router.get(
    "/payables/import/templates",
    response_model=list[PayableImportTemplateRead],
    dependencies=[Depends(require_permission(PAYABLES_UPDATE))],
)
async def list_payables_import_templates(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PayableImportTemplateRead]:
    return await PayableManualImportService(db).list_templates(user.id)


@router.post(
    "/payables/import/templates",
    response_model=PayableImportTemplateRead,
    dependencies=[Depends(require_permission(PAYABLES_UPDATE))],
)
async def create_payables_import_template(
    payload: PayableImportTemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PayableImportTemplateRead:
    try:
        row = await PayableManualImportService(db).create_template(user.id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return row


@router.delete(
    "/payables/import/templates/{template_id}",
    status_code=204,
    dependencies=[Depends(require_permission(PAYABLES_UPDATE))],
)
async def delete_payables_import_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    ok = await PayableManualImportService(db).delete_template(user.id, template_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Modelo não encontrado.")
    await db.commit()


@router.post(
    "/payables/import/preview",
    response_model=PayableImportPreviewResult,
    dependencies=[Depends(require_permission(PAYABLES_UPDATE))],
)
async def preview_payables_import(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> PayableImportPreviewResult:
    content, filename = await _read_payables_import_file(file)
    try:
        return await PayableManualImportService(db).preview(content, filename=filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/payables/import/confirm",
    response_model=PayableImportConfirmResult,
    dependencies=[Depends(require_permission(PAYABLES_UPDATE))],
)
async def confirm_payables_import(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> PayableImportConfirmResult:
    content, filename = await _read_payables_import_file(file)
    try:
        result = await PayableManualImportService(db).confirm(content, filename=filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return result


@router.post("/payables", response_model=PayableSnapshotRead, dependencies=[Depends(require_permission(PAYABLES_UPDATE))])
async def create_manual_payables_snapshot(
    payload: PayableSnapshotManualCreate,
    db: AsyncSession = Depends(get_db),
    # `redact_for` no retorno precisa do usuário. Sem esta dependência o handler estourava
    # NameError DEPOIS do commit: a despesa era gravada e o front recebia "Network Error"
    # (um 500 não passa pelo middleware de CORS, então o browser não mostra o status real).
    user: User = Depends(get_current_user),
) -> PayableSnapshotRead:
    # Exige snapshot do mês já gerado (via GET) para manter consistência.
    fin = FinanceService(db)
    month = normalize_competencia(payload.month)
    if not await fin.payable_snapshots.is_generated(month=month):
        raise HTTPException(status_code=409, detail="Gere o snapshot do mês antes de incluir despesas avulsas.")

    try:
        row = await fin.payable_snapshots.create_manual(
            month=month,
            name=payload.name,
            category=payload.category,
            cost_center=payload.cost_center,
            amount=payload.amount,
            due_date=payload.due_date,
            include_in_dashboard=payload.include_in_dashboard,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await db.commit()
    return redact_for("payables", _snapshot_to_read(row), user)


@router.delete("/payables/{snapshot_id}", status_code=204, dependencies=[Depends(require_permission(PAYABLES_UPDATE))])
async def delete_payables_snapshot(
    snapshot_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    svc = FinanceService(db).payable_snapshots
    row = await svc.get(snapshot_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    if row.type != PayableSnapshotType.MANUAL:
        if not await svc.can_delete_orphaned_row(row=row):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Exclusão não permitida. Pode excluir: itens MANUAL, linhas órfãs "
                    "(cuja origem foi removida) e duplicatas (quando há outra linha para a "
                    "mesma obrigação) — em todos os casos, sem pagamentos ativos. "
                    "Se houver pagamento, estorne primeiro."
                ),
            )
    await _ensure_payable_snapshot_edit_access(row=row, user=user, db=db)
    await svc.delete_row(row=row)
    await db.commit()


@router.post(
    "/payables/reconcile",
    response_model=PayableSnapshotReconcileResult,
    dependencies=[Depends(require_permission(PAYABLE_SNAPSHOT_RECONCILE))],
)
async def reconcile_payables_snapshot(
    month: str = Query(..., description="Mês do snapshot a reconciliar (YYYY-MM)."),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PayableSnapshotReconcileResult:
    """Marca lançamentos automáticos cujo origem foi removida como obsoletos
    (resíduos), sem apagar histórico. Restrito à competência informada."""
    comp = _parse_month(month)
    svc = FinanceService(db).payable_snapshots
    if not await svc.is_generated(month=comp):
        raise HTTPException(
            status_code=409, detail="Gere o snapshot do mês antes de reconciliar."
        )
    result = await svc.reconcile_snapshot(month=comp, user_id=user.id)
    await db.commit()
    return PayableSnapshotReconcileResult.model_validate(result)
