from __future__ import annotations

import calendar
from datetime import date


def normalize_competencia(d: date | str) -> date:
    """Competência sempre como primeiro dia do mês (evita mismatch em queries e unique).

    Aceita `date`/`datetime` ou string ISO (`YYYY-MM-DD` / `YYYY-MM`). A tolerância a string
    é deliberada: valores de competência circulam serializados (payloads JSON e dicionários
    de auditoria via `model_to_dict`, que converte datas com `.isoformat()`). Antes, uma
    string chegava aqui e quebrava com `AttributeError` — em `delete_labor` esse erro era
    engolido por um `except Exception`, deixando o lançamento de Contas a Pagar do mês
    seguinte órfão. Entrada inválida falha ALTO (ValueError/TypeError), nunca em silêncio.
    """
    if isinstance(d, str):
        raw = d.strip()
        if len(raw) == 7:  # YYYY-MM
            raw = f"{raw}-01"
        d = date.fromisoformat(raw)
    if not isinstance(d, date):
        raise TypeError(f"Competência deve ser date ou string ISO; recebido {type(d).__name__}.")
    return date(d.year, d.month, 1)


def previous_competencia(comp: date) -> date:
    """Primeiro dia do mês anterior (para cópia automática de mão de obra)."""
    comp = normalize_competencia(comp)
    if comp.month == 1:
        return date(comp.year - 1, 12, 1)
    return date(comp.year, comp.month - 1, 1)


def next_competencia(comp: date) -> date:
    comp = normalize_competencia(comp)
    if comp.month == 12:
        return date(comp.year + 1, 1, 1)
    return date(comp.year, comp.month + 1, 1)


def iter_competencias_inclusive(start: date, end: date) -> list[date]:
    """Meses (primeiro dia) de start a end, inclusive; start e end normalizados."""
    s = normalize_competencia(start)
    e = normalize_competencia(end)
    if s > e:
        return []
    out: list[date] = []
    cur = s
    while cur <= e:
        out.append(cur)
        cur = next_competencia(cur)
    return out


def first_day_n_months_before(anchor: date, n: int) -> date:
    """Primeiro dia do mês que está `n` meses antes de `anchor` (n=0 → próprio mês de anchor)."""
    cur = normalize_competencia(anchor)
    for _ in range(n):
        cur = previous_competencia(cur)
    return cur


def period_last_n_months(anchor: date, n: int) -> tuple[date, date]:
    """Últimos n meses com fim em anchor (inclusive). n >= 1."""
    end = normalize_competencia(anchor)
    start = first_day_n_months_before(end, n - 1)
    return start, end


def get_business_days(year: int, month: int) -> int:
    """Conta dias úteis (segunda a sexta) no mês; ignora sábado e domingo."""
    _, last_day = calendar.monthrange(year, month)
    count = 0
    for day in range(1, last_day + 1):
        wd = date(year, month, day).weekday()
        if wd < 5:
            count += 1
    return count
