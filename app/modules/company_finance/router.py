from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, require_permission
from app.core.permission_codes import COMPANY_FINANCE_EDIT, COMPANY_FINANCE_VIEW
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
)
from app.services.company_finance_service import CompanyFinanceService, parse_month


_read = [Depends(require_permission(COMPANY_FINANCE_VIEW))]

router = APIRouter()


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
        .options(selectinload(CompanyFinancialItem.payments))
    )
    return (await db.execute(q)).scalars().unique().one_or_none()


@router.get("/items", response_model=list[CompanyFinancialItemRead], dependencies=_read)
async def list_items(
    tipo: str = Query(..., pattern="^(endividamento|custo_fixo)$"),
    competencia: str | None = Query(default=None, description="YYYY-MM — mês de contexto para pago no mês"),
    db: AsyncSession = Depends(get_db),
) -> list[CompanyFinancialItemRead]:
    svc = CompanyFinanceService(db)
    comp = competencia or _default_month()
    rows = await svc.list_items(tipo=tipo, competencia=comp)
    return [CompanyFinancialItemRead.model_validate(r) for r in rows]


@router.post("/items", response_model=CompanyFinancialItemRead, dependencies=[Depends(require_permission(COMPANY_FINANCE_EDIT))])
async def create_item(
    payload: CompanyFinancialItemCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> CompanyFinancialItemRead:
    svc = CompanyFinanceService(db)
    row = await svc.create_item(actor_user_id=actor.id, data=payload.model_dump())
    await db.commit()
    loaded = await _load_item(db, row.id)
    if loaded is None:
        raise HTTPException(status_code=500, detail="Falha ao carregar item")
    comp = _default_month()
    read = svc._item_to_read(loaded, parse_month(comp))
    return CompanyFinancialItemRead.model_validate(read)


@router.patch("/items/{item_id}", response_model=CompanyFinancialItemRead, dependencies=[Depends(require_permission(COMPANY_FINANCE_EDIT))])
async def update_item(
    item_id: UUID,
    payload: CompanyFinancialItemUpdate,
    competencia: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> CompanyFinancialItemRead:
    _ = actor
    svc = CompanyFinanceService(db)
    row = await svc.update_item(item_id=item_id, data=payload.model_dump(exclude_unset=True))
    if row is None:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    await db.commit()
    loaded = await _load_item(db, item_id)
    if loaded is None:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    comp = competencia or _default_month()
    read = svc._item_to_read(loaded, parse_month(comp))
    return CompanyFinancialItemRead.model_validate(read)


@router.delete("/items/{item_id}", status_code=204, dependencies=[Depends(require_permission(COMPANY_FINANCE_EDIT))])
async def delete_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> None:
    _ = actor
    svc = CompanyFinanceService(db)
    ok = await svc.delete_item(item_id=item_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    await db.commit()


@router.put("/items/{item_id}/payments", response_model=CompanyFinancialItemRead, dependencies=[Depends(require_permission(COMPANY_FINANCE_EDIT))])
async def replace_payments(
    item_id: UUID,
    payload: PagamentosReplace,
    competencia: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> CompanyFinancialItemRead:
    _ = actor
    svc = CompanyFinanceService(db)
    pags = [p.model_dump() for p in payload.pagamentos]
    row = await svc.replace_payments(item_id=item_id, pagamentos=pags)
    if row is None:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    await db.commit()
    loaded = await _load_item(db, item_id)
    if loaded is None:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    comp = competencia or _default_month()
    read = svc._item_to_read(loaded, parse_month(comp))
    return CompanyFinancialItemRead.model_validate(read)


@router.get("/kpis/endividamento", response_model=KpiEndividamentoRead, dependencies=_read)
async def kpis_endividamento(
    competencia: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
) -> KpiEndividamentoRead:
    svc = CompanyFinanceService(db)
    data = await svc.kpis_endividamento(competencia=competencia)
    return KpiEndividamentoRead.model_validate(data)


@router.get("/kpis/custos-fixos", response_model=KpiCustosFixosRead, dependencies=_read)
async def kpis_custos_fixos(
    competencia: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
) -> KpiCustosFixosRead:
    svc = CompanyFinanceService(db)
    data = await svc.kpis_custos_fixos(competencia=competencia)
    return KpiCustosFixosRead.model_validate(data)


@router.get("/chart-series", response_model=ChartSeriesRead, dependencies=_read)
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
