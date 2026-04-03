from __future__ import annotations

import calendar
from datetime import date


def normalize_competencia(d: date) -> date:
    """Competência sempre como primeiro dia do mês (evita mismatch em queries e unique)."""
    return date(d.year, d.month, 1)


def get_business_days(year: int, month: int) -> int:
    """Conta dias úteis (segunda a sexta) no mês; ignora sábado e domingo."""
    _, last_day = calendar.monthrange(year, month)
    count = 0
    for day in range(1, last_day + 1):
        wd = date(year, month, day).weekday()
        if wd < 5:
            count += 1
    return count
