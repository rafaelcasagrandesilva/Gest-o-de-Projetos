from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tax_regime import TaxRegimePeriod


def normalize_start_date(d: date) -> date:
    """Regimes valem por competência: a vigência sempre começa no 1º dia do mês."""
    return d.replace(day=1)


class TaxRegimeService:
    """Vigências do regime tributário (Configurações).

    Só persistência: o cálculo dos impostos por regime mora em `app/services/tax_calc.py`,
    que consome `periods_as_tuples()`.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_periods(self) -> list[TaxRegimePeriod]:
        stmt = select(TaxRegimePeriod).order_by(TaxRegimePeriod.start_date.asc())
        return list((await self.db.execute(stmt)).scalars().all())

    async def periods_as_tuples(self) -> list[tuple[date, str]]:
        """[(start_date, regime), ...] em ordem crescente de início."""
        rows = (
            await self.db.execute(
                select(TaxRegimePeriod.start_date, TaxRegimePeriod.regime).order_by(
                    TaxRegimePeriod.start_date.asc()
                )
            )
        ).all()
        return [(start, regime) for start, regime in rows]

    async def create_period(self, data: dict) -> TaxRegimePeriod:
        """Cria uma vigência. `ValueError` (→ 400) se já existir outra no mesmo mês."""
        start = normalize_start_date(data["start_date"])
        taken = (
            await self.db.execute(
                select(func.count())
                .select_from(TaxRegimePeriod)
                .where(TaxRegimePeriod.start_date == start)
            )
        ).scalar_one()
        if taken:
            raise ValueError(
                f"Já existe um regime cadastrado a partir de {start.strftime('%m/%Y')}. "
                "Remova-o antes de cadastrar outro no mesmo mês."
            )
        note = (data.get("note") or "").strip() or None
        row = TaxRegimePeriod(regime=data["regime"], start_date=start, note=note)
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def delete_period(self, period_id: UUID) -> bool:
        """Remove uma vigência. False (→ 404) se não existe; `ValueError` (→ 400) se é a única."""
        row = await self.db.get(TaxRegimePeriod, period_id)
        if row is None:
            return False
        total = (
            await self.db.execute(select(func.count()).select_from(TaxRegimePeriod))
        ).scalar_one()
        if total <= 1:
            raise ValueError(
                "Não é possível remover o único regime cadastrado. "
                "Cadastre o novo regime antes de remover este."
            )
        await self.db.delete(row)
        await self.db.flush()
        return True
