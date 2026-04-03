"""
Recalcula total_cost de colaboradores CLT com a regra vigente (competência + encargos + VR).

Uso:
  python -m app.scripts.recalculate_employee_costs --year 2026 --month 4
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date

from sqlalchemy import select

from app.database.session import AsyncSessionLocal
from app.models.employee import Employee
from app.services.employee_cost_service import calculate_clt_cost
from app.services.settings_service import SettingsService


async def run(*, year: int, month: int) -> int:
    async with AsyncSessionLocal() as session:
        settings = await SettingsService(session).get_or_create()
        res = await session.execute(select(Employee).where(Employee.employment_type == "CLT"))
        rows = list(res.scalars().all())
        for emp in rows:
            emp.total_cost = calculate_clt_cost(emp, settings, year, month)
        await session.commit()
        return len(rows)


def main() -> None:
    p = argparse.ArgumentParser(description="Recalcular total_cost dos CLTs para uma competência.")
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--month", type=int, required=True, choices=range(1, 13))
    args = p.parse_args()
    date(args.year, args.month, 1)
    n = asyncio.run(run(year=args.year, month=args.month))
    print(f"Atualizados {n} colaborador(es) CLT para {args.year:04d}-{args.month:02d}.")


if __name__ == "__main__":
    main()
