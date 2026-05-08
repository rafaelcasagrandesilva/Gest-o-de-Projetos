from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import MissingGreenlet

from app.api.deps import (
    assert_may_write_scenario,
    default_scenario_for_create,
    ensure_project_access,
    get_accessible_project_ids,
    get_current_user,
    get_current_workspace,
    is_app_superuser,
    require_permission,
    user_sees_all_projects,
)
from app.core.permission_codes import (
    BILLING_VIEW,
    COSTS_EDIT,
    INVOICES_EDIT,
    INVOICES_VIEW,
    PAYABLES_VIEW,
    RECEIVABLES_VIEW,
)
from app.core.scenario import coerce_scenario, parse_scenario
from app.database.session import get_db
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
from app.models.payable_snapshot import PayableSnapshotType
from app.schemas.payables import (
    PayableSnapshotManualCreate,
    PayableSnapshotPaymentBody,
    PayableSnapshotRead,
    PayableSnapshotUpdate,
)
from app.services.financial_crud_service import FinancialCrudService
from app.services.finance_service import FinanceService
from app.services.payable_snapshot_service import payable_snapshot_payment_status
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
from app.schemas.financial_dashboard import (
    FinancialDashboardBreakdownRead,
    FinancialDashboardGroupedItem,
    FinancialDashboardRead,
    FinancialDashboardSummaryRead,
    FinancialDashboardTimeseriesPoint,
)
from app.services.financial_dashboard_service import FinancialDashboardService


_read = [Depends(require_permission(BILLING_VIEW))]

router = APIRouter()


def _receivable_view_status(*, net_value: float, total_received: float) -> str:
    net = float(net_value or 0.0)
    recv = float(total_received or 0.0)
    if recv <= 0:
        return "ABERTO"
    if recv + 0.01 < net:
        return "PARCIAL"
    return "RECEBIDO"


@router.get("/receivables", response_model=list[ReceivableViewRead], dependencies=[Depends(require_permission(RECEIVABLES_VIEW))])
async def list_receivables_view(
    request: Request,
    project_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(EMITIDA|ANTECIPADA|RECEBIDA|CANCELADA)$"),
    client: str | None = Query(default=None, max_length=255),
    tipo: str | None = Query(default=None, pattern="^(NF|MANUAL|ANTECIPACAO)$"),
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
            # NF cancelada nunca deve aparecer na visão de contas a receber.
            if (inv.invoice_status or "").upper() == "CANCELADA":
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
                    )
                )
    return out


@router.post(
    "/receivables/manual",
    response_model=ReceivableManualItemRead,
    dependencies=[Depends(require_permission(INVOICES_EDIT))],
)
async def create_receivable_manual_item(
    payload: ReceivableManualItemCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _ws: str = Depends(get_current_workspace),
) -> ReceivableManualItemRead:
    svc = ReceivableManualService(db)
    data = payload.model_dump()
    try:
        row = await svc.create(workspace_id=request.state.workspace, data=data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return ReceivableManualItemRead.model_validate(row, from_attributes=True)


@router.patch(
    "/receivables/manual/{item_id}",
    response_model=ReceivableManualItemRead,
    dependencies=[Depends(require_permission(INVOICES_EDIT))],
)
async def update_receivable_manual_item(
    item_id: UUID,
    payload: ReceivableManualItemUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
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
    return ReceivableManualItemRead.model_validate(row, from_attributes=True)


@router.delete(
    "/receivables/manual/{item_id}",
    status_code=204,
    dependencies=[Depends(require_permission(INVOICES_EDIT))],
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
    return [RevenueRead.model_validate(r) for r in rows]


@router.post("/revenues", response_model=RevenueRead, dependencies=[Depends(require_permission(INVOICES_EDIT))])
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
    return RevenueRead.model_validate(row)


@router.patch("/revenues/{revenue_id}", response_model=RevenueRead, dependencies=[Depends(require_permission(INVOICES_EDIT))])
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
    return RevenueRead.model_validate(row)


@router.delete("/revenues/{revenue_id}", status_code=204, dependencies=[Depends(require_permission(INVOICES_EDIT))])
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


@router.get("/invoices", response_model=list[InvoiceRead], dependencies=[Depends(require_permission(INVOICES_VIEW))])
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
    return [InvoiceRead.model_validate(r) for r in rows]


@router.post("/invoices", response_model=InvoiceRead, dependencies=[Depends(require_permission(INVOICES_EDIT))])
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
    return InvoiceRead.model_validate(row)


@router.post("/invoices/anticipations", response_model=InvoiceAnticipationRead, dependencies=[Depends(require_permission(INVOICES_EDIT))])
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
    return InvoiceAnticipationRead.model_validate(row)


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
    dependencies=[Depends(require_permission(BILLING_VIEW))],
)
async def financial_dashboard(
    month: str = Query(..., description="Mês âncora (YYYY-MM)."),
    months: int = Query(default=1, ge=1, le=24, description="Período (em meses)."),
    db: AsyncSession = Depends(get_db),
    workspace: str = Depends(get_current_workspace),
) -> FinancialDashboardRead:
    comp = _parse_month(month)
    svc = FinancialDashboardService(db)
    summary, points = await svc.cash_summary_and_series(month=comp, months=months, workspace_id=workspace)
    await db.commit()
    return FinancialDashboardRead(
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
    )


@router.get(
    "/dashboard/timeseries",
    response_model=list[FinancialDashboardTimeseriesPoint],
    dependencies=[Depends(require_permission(BILLING_VIEW))],
)
async def financial_dashboard_timeseries(
    month: str = Query(..., description="Mês âncora (YYYY-MM)."),
    months: int = Query(default=12, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    workspace: str = Depends(get_current_workspace),
) -> list[FinancialDashboardTimeseriesPoint]:
    comp = _parse_month(month)
    svc = FinancialDashboardService(db)
    _, points = await svc.cash_summary_and_series(month=comp, months=months, workspace_id=workspace)
    await db.commit()
    return [
        FinancialDashboardTimeseriesPoint(
            month=p.month,
            faturamento=p.faturamento,
            pago=p.pago,
            caixa=p.caixa,
        )
        for p in points
    ]


@router.get(
    "/dashboard/breakdown",
    response_model=FinancialDashboardBreakdownRead,
    dependencies=[Depends(require_permission(BILLING_VIEW))],
)
async def financial_dashboard_breakdown(
    type: str = Query(..., pattern="^(faturamento|custos|caixa)$"),
    month: str = Query(..., description="Mês (YYYY-MM)."),
    db: AsyncSession = Depends(get_db),
    workspace: str = Depends(get_current_workspace),
) -> FinancialDashboardBreakdownRead:
    comp = _parse_month(month)
    svc = FinancialDashboardService(db)
    total, groups, received_total, received_groups, paid_total, paid_groups = await svc.cash_breakdown(
        type=type, month=comp, workspace_id=workspace
    )
    await db.commit()
    return FinancialDashboardBreakdownRead(
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
    )


def _snapshot_to_read(row) -> PayableSnapshotRead:
    amount_final = float(row.amount_final)
    amount_paid = float(row.amount_paid or 0)
    amount_remaining = round(max(0.0, amount_final - amount_paid), 2)
    st = payable_snapshot_payment_status(
        amount_paid=Decimal(str(amount_paid)),
        amount_final=Decimal(str(amount_final)),
    )
    paid_flag = st == "PAGO"
    return PayableSnapshotRead(
        id=row.id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        month=row.month,
        type=row.type.value,
        ref_id=row.ref_id,
        project_id=row.project_id,
        name=row.name,
        cost_center=row.cost_center,
        category=row.category,
        amount_original=float(row.amount_original),
        amount_final=amount_final,
        amount_paid=amount_paid,
        amount_remaining=amount_remaining,
        due_date=row.due_date,
        payment_date=row.payment_date,
        paid=paid_flag,
        observation=row.observation,
        status=st,
    )


@router.get("/payables", response_model=list[PayableSnapshotRead], dependencies=[Depends(require_permission(PAYABLES_VIEW))])
async def list_payables_snapshot(
    month: str | None = Query(default=None, description="Mês de competência do pagamento (YYYY-MM). Omitir = todos."),
    force_regenerate: bool = Query(default=False, description="Regerar snapshot do mês (apaga snapshot existente)."),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PayableSnapshotRead]:
    if force_regenerate and not is_app_superuser(user):
        raise HTTPException(
            status_code=403,
            detail="Apenas contas super usuário podem regerar o snapshot de contas a pagar.",
        )
    sees_all = user_sees_all_projects(user)
    allowed = None if sees_all else set(await get_accessible_project_ids(user, db))
    if not sees_all and (not allowed):
        # Financeiro ignora escopo de project_users: fallback para todos projetos.
        all_ids = await ProjectRepository(db).list_all_project_ids()
        allowed = set(all_ids)

    # month omitido: retorna todos os snapshots já salvos (não gera em massa).
    if month is None or (isinstance(month, str) and not month.strip()):
        rows = await FinanceService(db).payable_snapshots.list_all()
        await db.commit()
        return [_snapshot_to_read(r) for r in rows]

    comp = _parse_month(month)

    try:
        rows = await FinanceService(db).get_or_create_payables_snapshot(
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

    if not sees_all and allowed is not None:
        filtered = []
        for r in rows:
            if r.type in (PayableSnapshotType.VEHICLE, PayableSnapshotType.FIXED_COST, PayableSnapshotType.MANUAL):
                filtered.append(r)
                continue
            if r.type == PayableSnapshotType.COLLABORATOR and r.project_id in allowed:
                filtered.append(r)
        rows = filtered

    await db.commit()
    return [_snapshot_to_read(r) for r in rows]


async def _ensure_payable_snapshot_edit_access(*, row, user: User, db: AsyncSession) -> None:
    if not user_sees_all_projects(user):
        allowed = set(await get_accessible_project_ids(user, db))
        if not allowed:
            allowed = set(await ProjectRepository(db).list_all_project_ids())
        if row.type == PayableSnapshotType.COLLABORATOR and row.project_id not in allowed:
            raise HTTPException(status_code=403, detail="Sem permissão.")


@router.patch("/payables/{snapshot_id}", response_model=PayableSnapshotRead, dependencies=[Depends(require_permission(COSTS_EDIT))])
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
    )
    await db.commit()
    return _snapshot_to_read(updated)


@router.post(
    "/payables/{snapshot_id}/register-payment",
    response_model=PayableSnapshotRead,
    dependencies=[Depends(require_permission(COSTS_EDIT))],
)
async def register_payables_payment(
    snapshot_id: UUID,
    payload: PayableSnapshotPaymentBody,
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
            row=row, amount=payload.amount, observation=payload.observation
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await db.commit()
    return _snapshot_to_read(updated)


@router.post(
    "/payables/{snapshot_id}/reverse-payment",
    response_model=PayableSnapshotRead,
    dependencies=[Depends(require_permission(COSTS_EDIT))],
)
async def reverse_payables_payment(
    snapshot_id: UUID,
    payload: PayableSnapshotPaymentBody,
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
            row=row, amount=payload.amount, observation=payload.observation
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await db.commit()
    return _snapshot_to_read(updated)


@router.post("/payables", response_model=PayableSnapshotRead, dependencies=[Depends(require_permission(COSTS_EDIT))])
async def create_manual_payables_snapshot(
    payload: PayableSnapshotManualCreate,
    db: AsyncSession = Depends(get_db),
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
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await db.commit()
    return _snapshot_to_read(row)


@router.delete("/payables/{snapshot_id}", status_code=204, dependencies=[Depends(require_permission(COSTS_EDIT))])
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
        raise HTTPException(status_code=400, detail="Somente itens MANUAL podem ser excluídos.")
    await _ensure_payable_snapshot_edit_access(row=row, user=user, db=db)
    await svc.delete_row(row=row)
    await db.commit()
