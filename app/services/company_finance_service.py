from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.company_finance import CompanyFinancialItem, CompanyFinancialPayment
from app.schemas.company_finance import PagamentoMes


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def parse_month(s: str) -> date:
    parts = s.strip().split("-")
    if len(parts) != 2:
        raise ValueError("mes inválido")
    y, m = int(parts[0]), int(parts[1])
    return date(y, m, 1)


def _f(v: object) -> float:
    return float(v) if v is not None else 0.0


class CompanyFinanceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_items(self, tipo: str, competencia: str | None) -> list[dict]:
        q = (
            select(CompanyFinancialItem)
            .where(CompanyFinancialItem.tipo == tipo)
            .options(selectinload(CompanyFinancialItem.payments))
            .order_by(CompanyFinancialItem.nome)
        )
        rows = (await self.db.execute(q)).scalars().unique().all()
        comp_date = parse_month(competencia) if competencia else None
        return [self._item_to_read(it, comp_date) for it in rows]

    def _item_to_read(self, it: CompanyFinancialItem, competencia: date | None) -> dict:
        pags = sorted(it.payments, key=lambda p: p.competencia)
        pagamentos = [PagamentoMes(mes=month_key(p.competencia), valor=_f(p.valor)).model_dump() for p in pags]
        total_pago = sum(_f(p.valor) for p in it.payments)
        ref = _f(it.valor_referencia)
        pago_mes = 0.0
        if competencia:
            for p in it.payments:
                if p.competencia == competencia:
                    pago_mes = _f(p.valor)
                    break

        if it.tipo == "endividamento":
            restante = max(0.0, ref - total_pago)
            progresso = (total_pago / ref) if ref > 0 else 0.0
            status = "quitado" if progresso >= 1.0 else "ativo"
            return {
                "id": it.id,
                "tipo": it.tipo,
                "nome": it.nome,
                "valor_referencia": ref,
                "pagamentos": pagamentos,
                "total_pago": total_pago,
                "restante": restante,
                "progresso": min(1.0, progresso),
                "status": status,
                "progresso_mes": None,
                "pago_mes": pago_mes,
            }

        progresso_mes = (pago_mes / ref) if ref > 0 else 0.0
        return {
            "id": it.id,
            "tipo": it.tipo,
            "nome": it.nome,
            "valor_referencia": ref,
            "pagamentos": pagamentos,
            "total_pago": total_pago,
            "restante": None,
            "progresso": progresso_mes,
            "status": None,
            "progresso_mes": progresso_mes,
            "pago_mes": pago_mes,
        }

    async def create_item(self, *, actor_user_id: UUID, data: dict) -> CompanyFinancialItem:
        row = CompanyFinancialItem(
            tipo=data["tipo"],
            nome=data["nome"].strip(),
            valor_referencia=data["valor_referencia"],
        )
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def update_item(self, *, item_id: UUID, data: dict) -> CompanyFinancialItem | None:
        row = await self.db.get(CompanyFinancialItem, item_id)
        if row is None:
            return None
        if data.get("nome") is not None:
            row.nome = data["nome"].strip()
        if data.get("valor_referencia") is not None:
            row.valor_referencia = data["valor_referencia"]
        row.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def delete_item(self, *, item_id: UUID) -> bool:
        row = await self.db.get(CompanyFinancialItem, item_id)
        if row is None:
            return False
        await self.db.delete(row)
        await self.db.flush()
        return True

    async def replace_payments(self, *, item_id: UUID, pagamentos: list[dict]) -> CompanyFinancialItem | None:
        item = await self.db.get(CompanyFinancialItem, item_id)
        if item is None:
            return None
        await self.db.execute(delete(CompanyFinancialPayment).where(CompanyFinancialPayment.item_id == item_id))
        for p in pagamentos:
            mes = p["mes"]
            comp = parse_month(mes)
            val = max(0.0, float(p.get("valor") or 0))
            if val <= 0:
                continue
            self.db.add(
                CompanyFinancialPayment(
                    item_id=item_id,
                    competencia=comp,
                    valor=val,
                )
            )
        item.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(item, attribute_names=["payments"])
        return item

    async def kpis_endividamento(self, competencia: str) -> dict:
        items = (
            (
                await self.db.execute(
                    select(CompanyFinancialItem)
                    .where(CompanyFinancialItem.tipo == "endividamento")
                    .options(selectinload(CompanyFinancialItem.payments))
                )
            )
            .scalars()
            .unique()
            .all()
        )
        comp = parse_month(competencia)
        total_endividamento = sum(_f(i.valor_referencia) for i in items)
        total_pago_mes = 0.0
        saldo_restante = 0.0
        for it in items:
            ref = _f(it.valor_referencia)
            total_pago = sum(_f(p.valor) for p in it.payments)
            total_pago_mes += sum(_f(p.valor) for p in it.payments if p.competencia == comp)
            saldo_restante += max(0.0, ref - total_pago)
        return {
            "total_endividamento": total_endividamento,
            "total_pago_mes": total_pago_mes,
            "saldo_restante": saldo_restante,
            "quantidade_itens": len(items),
        }

    async def kpis_custos_fixos(self, competencia: str) -> dict:
        items = (
            (
                await self.db.execute(
                    select(CompanyFinancialItem)
                    .where(CompanyFinancialItem.tipo == "custo_fixo")
                    .options(selectinload(CompanyFinancialItem.payments))
                )
            )
            .scalars()
            .unique()
            .all()
        )
        comp = parse_month(competencia)
        total_esperado_mes = sum(_f(i.valor_referencia) for i in items)
        total_pago_mes = 0.0
        for it in items:
            for p in it.payments:
                if p.competencia == comp:
                    total_pago_mes += _f(p.valor)
                    break
        return {
            "total_esperado_mes": total_esperado_mes,
            "total_pago_mes": total_pago_mes,
            "quantidade_itens": len(items),
        }

    async def chart_series(self, tipo: str, mes_inicio: str, mes_fim: str) -> list[dict]:
        items = (
            (
                await self.db.execute(
                    select(CompanyFinancialItem)
                    .where(CompanyFinancialItem.tipo == tipo)
                    .options(selectinload(CompanyFinancialItem.payments))
                )
            )
            .scalars()
            .unique()
            .all()
        )
        start = parse_month(mes_inicio)
        end = parse_month(mes_fim)
        if start > end:
            start, end = end, start

        months: list[date] = []
        cur = date(start.year, start.month, 1)
        end_m = date(end.year, end.month, 1)
        while cur <= end_m:
            months.append(cur)
            if cur.month == 12:
                cur = date(cur.year + 1, 1, 1)
            else:
                cur = date(cur.year, cur.month + 1, 1)

        points: list[dict] = []
        for m in months:
            mk = month_key(m)
            pagamentos_mes = 0.0
            for it in items:
                for p in it.payments:
                    if p.competencia == m:
                        pagamentos_mes += _f(p.valor)
                        break

            saldo_restante_total = None
            if tipo == "endividamento":
                saldo_restante_total = 0.0
                for it in items:
                    ref = _f(it.valor_referencia)
                    cum = sum(_f(p.valor) for p in it.payments if p.competencia <= m)
                    saldo_restante_total += max(0.0, ref - cum)

            points.append(
                {
                    "mes": mk,
                    "pagamentos_mes": pagamentos_mes,
                    "saldo_restante_total": saldo_restante_total,
                }
            )
        return points
