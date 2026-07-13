from __future__ import annotations

import logging
import traceback
from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, require_permission, user_has_permission
from app.core.permission_codes import (
    COMPANY_FINANCE_EDIT,
    COMPANY_FINANCE_VIEW,
    DEBTS_EDIT,
    DEBTS_VIEW,
)
from app.database.session import get_db
from app.models.company_finance import CompanyFinancialItem
from app.models.user import User
from app.schemas.company_finance import (
    ChartSeriesRead,
    ChartPoint,
    CompanyFinancialItemCreate,
    CompanyFinancialItemRead,
    CompanyFinancialItemUpdate,
    KpiCustosFixosRead,
    KpiEndividamentoRead,
    PagamentosReplace,
    PendenciasCustosFixosRead,
)
from app.services.company_finance_service import CompanyFinanceService, parse_month


router = APIRouter()
logger = logging.getLogger(__name__)


# --- Autorização por TIPO (isolamento de módulos) -----------------------------------------
# Endividamento e Custos Fixos-Matriz compartilham os mesmos endpoints, distinguidos pelo `tipo`.
# Cada um usa a permissão do SEU módulo, sem depender do outro:
#   - tipo == "endividamento" -> debts.view / debts.edit
#   - tipo == "custo_fixo"    -> company_finance.view / company_finance.edit
def _view_code_for_tipo(tipo: str) -> str:
    return DEBTS_VIEW if tipo == "endividamento" else COMPANY_FINANCE_VIEW


def _edit_code_for_tipo(tipo: str) -> str:
    return DEBTS_EDIT if tipo == "endividamento" else COMPANY_FINANCE_EDIT


def _assert_view(user: User, tipo: str) -> None:
    if not user_has_permission(user, _view_code_for_tipo(tipo)):
        raise HTTPException(status_code=403, detail="Sem permissão para visualizar este módulo.")


def _assert_edit(user: User, tipo: str) -> None:
    if not user_has_permission(user, _edit_code_for_tipo(tipo)):
        raise HTTPException(status_code=403, detail="Sem permissão para editar este módulo.")


def require_finance_view_by_tipo(
    tipo: str = Query(..., pattern="^(endividamento|custo_fixo)$"),
    user: User = Depends(get_current_user),
) -> None:
    """Dependency de LEITURA para endpoints que recebem `tipo` na query."""
    _assert_view(user, tipo)


async def _item_tipo(db: AsyncSession, item_id: UUID) -> str | None:
    """Lê apenas o `tipo` de um item (para autorizar mutações por módulo)."""
    return (
        await db.execute(select(CompanyFinancialItem.tipo).where(CompanyFinancialItem.id == item_id))
    ).scalar_one_or_none()


_read_by_tipo = [Depends(require_finance_view_by_tipo)]


def _default_month() -> str:
    now = datetime.now().astimezone()
    return f"{now.year:04d}-{now.month:02d}"


def _month_range_default_end() -> tuple[str, str]:
    end_s = _default_month()
    y, m = int(end_s.split("-")[0]), int(end_s.split("-")[1])
    d = date(y, m, 1)
    for _ in range(11):
        if m == 1:
            y -= 1
            m = 12
        else:
            m -= 1
    start_s = f"{y:04d}-{m:02d}"
    return start_s, end_s


async def _load_item(db: AsyncSession, item_id: UUID) -> CompanyFinancialItem | None:
    q = (
        select(CompanyFinancialItem)
        .where(CompanyFinancialItem.id == item_id)
        .options(
            selectinload(CompanyFinancialItem.payments),
            selectinload(CompanyFinancialItem.employee),
            selectinload(CompanyFinancialItem.cost_center_project),
        )
    )
    return (await db.execute(q)).scalars().unique().one_or_none()


@router.get("/items", response_model=list[CompanyFinancialItemRead], dependencies=_read_by_tipo)
async def list_items(
    tipo: str = Query(..., pattern="^(endividamento|custo_fixo)$"),
    competencia: str | None = Query(default=None, description="YYYY-MM — mês de contexto para pago no mês"),
    db: AsyncSession = Depends(get_db),
) -> list[CompanyFinancialItemRead]:
    svc = CompanyFinanceService(db)
    comp = competencia or _default_month()
    rows = await svc.list_items(tipo=tipo, competencia=comp)
    return [CompanyFinancialItemRead.model_validate(r) for r in rows]


@router.post("/items", response_model=CompanyFinancialItemRead)
async def create_item(
    payload: CompanyFinancialItemCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> CompanyFinancialItemRead:
    _assert_edit(actor, payload.tipo)
    svc = CompanyFinanceService(db)
    try:
        row = await svc.create_item(actor_user_id=actor.id, data=payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    loaded = await _load_item(db, row.id)
    if loaded is None:
        raise HTTPException(status_code=500, detail="Falha ao carregar item")
    comp = _default_month()
    read = await svc._item_to_read(loaded, parse_month(comp))
    return CompanyFinancialItemRead.model_validate(read)


@router.patch("/items/{item_id}", response_model=CompanyFinancialItemRead)
async def update_item(
    item_id: UUID,
    payload: CompanyFinancialItemUpdate,
    competencia: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> CompanyFinancialItemRead:
    tipo = await _item_tipo(db, item_id)
    if tipo is None:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    _assert_edit(actor, tipo)
    svc = CompanyFinanceService(db)
    patch_data = payload.model_dump(exclude_unset=True)
    logger.info(
        "company_finance.patch_item item_id=%s competencia=%s payload=%s",
        item_id,
        competencia,
        patch_data,
    )
    try:
        row = await svc.update_item(item_id=item_id, data=patch_data)
    except ValueError as exc:
        logger.warning("company_finance.patch_item validation_error item_id=%s detail=%s", item_id, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    await db.commit()
    loaded = await _load_item(db, item_id)
    if loaded is None:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    comp = competencia or _default_month()
    read = await svc._item_to_read(loaded, parse_month(comp))
    logger.info(
        "company_finance.patch_item saved item_id=%s cost_center_ref=%s cost_center=%s project_id=%s system=%s",
        item_id,
        read.get("cost_center_ref"),
        read.get("cost_center"),
        read.get("cost_center_project_id"),
        read.get("cost_center_system"),
    )
    return CompanyFinancialItemRead.model_validate(read)


@router.delete("/items/{item_id}", status_code=204)
async def delete_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> None:
    tipo = await _item_tipo(db, item_id)
    if tipo is None:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    _assert_edit(actor, tipo)
    svc = CompanyFinanceService(db)
    try:
        ok = await svc.delete_item(item_id=item_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    await db.commit()


@router.put("/items/{item_id}/payments", response_model=CompanyFinancialItemRead)
async def replace_payments(
    item_id: UUID,
    payload: PagamentosReplace,
    competencia: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> CompanyFinancialItemRead:
    tipo = await _item_tipo(db, item_id)
    if tipo is None:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    _assert_edit(actor, tipo)
    pags = [p.model_dump() for p in payload.pagamentos]
    logger.info(
        "company_finance.replace_payments START item_id=%s competencia=%s payload=%s",
        item_id,
        competencia,
        pags,
    )
    try:
        svc = CompanyFinanceService(db)
        row = await svc.replace_payments(item_id=item_id, pagamentos=pags)
        if row is None:
            raise HTTPException(status_code=404, detail="Item não encontrado")

        logger.info("company_finance.replace_payments BEFORE commit item_id=%s", item_id)
        await db.commit()
        logger.info(
            "company_finance.replace_payments AFTER commit item_id=%s payment_count=%d",
            item_id,
            len(row.payments),
        )

        loaded = await _load_item(db, item_id)
        if loaded is None:
            raise HTTPException(status_code=404, detail="Item não encontrado")
        comp = competencia or _default_month()
        read = await svc._item_to_read(loaded, parse_month(comp))
        result = CompanyFinancialItemRead.model_validate(read)
        # Aviso quando a grade não pôde governar o CAP por já haver pagamento no mês.
        sync = svc.last_payable_sync or {}
        skipped = sync.get("skipped_paid") or []
        if skipped:
            meses = ", ".join(f"{d:%m/%Y}" for d in sorted(skipped))
            result.payable_sync_warning = (
                f"Existe pagamento registrado em {meses}: o Contas a Pagar não foi ajustado "
                "automaticamente. Ajuste o lançamento manualmente para preservar o histórico."
            )
        logger.info("company_finance.replace_payments OK item_id=%s competencia=%s", item_id, comp)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "company_finance.replace_payments FAILED item_id=%s competencia=%s payload=%s error=%s\n%s",
            item_id,
            competencia,
            pags,
            e,
            traceback.format_exc(),
        )
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/kpis/endividamento", response_model=KpiEndividamentoRead, dependencies=[Depends(require_permission(DEBTS_VIEW))])
async def kpis_endividamento(
    competencia: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
) -> KpiEndividamentoRead:
    svc = CompanyFinanceService(db)
    data = await svc.kpis_endividamento(competencia=competencia)
    return KpiEndividamentoRead.model_validate(data)


@router.get("/kpis/custos-fixos", response_model=KpiCustosFixosRead, dependencies=[Depends(require_permission(COMPANY_FINANCE_VIEW))])
async def kpis_custos_fixos(
    competencia: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
) -> KpiCustosFixosRead:
    svc = CompanyFinanceService(db)
    data = await svc.kpis_custos_fixos(competencia=competencia)
    return KpiCustosFixosRead.model_validate(data)


@router.get("/pendencias", response_model=PendenciasCustosFixosRead, dependencies=_read_by_tipo)
async def pendencias(
    tipo: str = Query(..., pattern="^(endividamento|custo_fixo)$"),
    competencia: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
) -> PendenciasCustosFixosRead:
    svc = CompanyFinanceService(db)
    data = await svc.pendencias(tipo=tipo, competencia=competencia)
    return PendenciasCustosFixosRead.model_validate(data)


@router.get("/pendencias/custos-fixos", response_model=PendenciasCustosFixosRead, dependencies=[Depends(require_permission(COMPANY_FINANCE_VIEW))])
async def pendencias_custos_fixos(
    competencia: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
) -> PendenciasCustosFixosRead:
    """Alias de compatibilidade — equivale a /pendencias?tipo=custo_fixo."""
    svc = CompanyFinanceService(db)
    data = await svc.pendencias_custos_fixos(competencia=competencia)
    return PendenciasCustosFixosRead.model_validate(data)


@router.get("/chart-series", response_model=ChartSeriesRead, dependencies=_read_by_tipo)
async def chart_series(
    tipo: str = Query(..., pattern="^(endividamento|custo_fixo)$"),
    mes_inicio: str | None = Query(default=None, description="YYYY-MM"),
    mes_fim: str | None = Query(default=None, description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
) -> ChartSeriesRead:
    svc = CompanyFinanceService(db)
    default_start, default_end = _month_range_default_end()
    end = mes_fim or default_end
    start = mes_inicio or default_start
    points_raw = await svc.chart_series(tipo=tipo, mes_inicio=start, mes_fim=end)
    points = [ChartPoint.model_validate(p) for p in points_raw]
    return ChartSeriesRead(points=points)
