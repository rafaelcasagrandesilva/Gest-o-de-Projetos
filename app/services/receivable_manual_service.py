from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.receivable_manual import ReceivableManualItem, ReceivableManualStatus
from app.utils.dashboard_inclusion import apply_dashboard_inclusion_change, append_observation_line


CENT_TOL = 0.009


def _as_money(v: float | Decimal | None) -> float:
    if v is None:
        return 0.0
    return float(v)


def derive_manual_status(*, valor_liquido: float, valor_recebido: float) -> ReceivableManualStatus:
    net = float(valor_liquido or 0.0)
    recv = float(valor_recebido or 0.0)
    if recv <= 0.0 + CENT_TOL:
        return ReceivableManualStatus.ABERTO
    if recv + CENT_TOL < net:
        return ReceivableManualStatus.PARCIAL
    return ReceivableManualStatus.RECEBIDO


class ReceivableManualService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, item_id: UUID) -> ReceivableManualItem | None:
        return await self.session.get(ReceivableManualItem, item_id)

    def _base_list_stmt(
        self,
        *,
        workspace_id: str,
        client: str | None,
        year: int | None,
        month: int | None,
        period_field: str,
    ) -> Select:
        stmt = select(ReceivableManualItem).where(ReceivableManualItem.workspace_id == workspace_id)
        if client:
            q = f"%{client.strip()}%"
            stmt = stmt.where(or_(ReceivableManualItem.cliente.ilike(q), ReceivableManualItem.descricao.ilike(q)))

        if year is not None and month is not None:
            field = ReceivableManualItem.data_emissao if period_field == "issue" else ReceivableManualItem.data_vencimento
            stmt = stmt.where(
                and_(
                    func.extract("year", field) == year,
                    func.extract("month", field) == month,
                )
            )
        return stmt.order_by(ReceivableManualItem.data_vencimento.desc(), ReceivableManualItem.created_at.desc())

    async def list(
        self,
        *,
        workspace_id: str,
        client: str | None,
        year: int | None,
        month: int | None,
        period_field: str,
    ) -> list[ReceivableManualItem]:
        stmt = self._base_list_stmt(
            workspace_id=workspace_id, client=client, year=year, month=month, period_field=period_field
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def create(self, *, workspace_id: str, data: dict) -> ReceivableManualItem:
        liq = float(data["valor_liquido"])
        rec = float(data.get("valor_recebido") or 0.0)
        if rec > liq + CENT_TOL:
            raise ValueError("valor_recebido não pode ser maior que valor_liquido.")
        status = derive_manual_status(valor_liquido=liq, valor_recebido=rec)
        row = ReceivableManualItem(
            workspace_id=workspace_id,
            descricao=data["descricao"],
            cliente=data["cliente"],
            numero_referencia=data.get("numero_referencia"),
            data_emissao=data["data_emissao"],
            data_vencimento=data["data_vencimento"],
            valor_liquido=liq,
            valor_recebido=rec,
            data_recebimento=data.get("data_recebimento"),
            observacao=data.get("observacao"),
            status=status,
            include_in_dashboard=bool(data.get("include_in_dashboard", True)),
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def update(self, *, item_id: UUID, data: dict) -> ReceivableManualItem:
        row = await self.get(item_id)
        if not row:
            raise LookupError("Receita manual não encontrada.")

        include_new = data.pop("include_in_dashboard", None)
        for k, v in data.items():
            setattr(row, k, v)
        apply_dashboard_inclusion_change(
            before=bool(row.include_in_dashboard),
            after=include_new,
            set_value=lambda v: setattr(row, "include_in_dashboard", v),
            append_line=lambda line: setattr(row, "observacao", append_observation_line(row.observacao, line)),
        )

        liq = _as_money(row.valor_liquido)
        rec = _as_money(row.valor_recebido)
        if rec > liq + CENT_TOL:
            raise ValueError("valor_recebido não pode ser maior que valor_liquido.")
        row.status = derive_manual_status(valor_liquido=liq, valor_recebido=rec)

        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def delete(self, *, item_id: UUID) -> None:
        await self.session.execute(delete(ReceivableManualItem).where(ReceivableManualItem.id == item_id))
        await self.session.commit()

