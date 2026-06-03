"""Normalização monetária BRL (reais, 2 casas). Mantém lógica alinhada a frontend/src/utils/currency.ts."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_MONEY_QUANT = Decimal("0.01")
_CURRENCY_DECOR = re.compile(r"R\$\s?", re.IGNORECASE)


def strip_currency_decorations(raw: str) -> str:
    return _CURRENCY_DECOR.sub("", raw).replace(" ", "").strip()


def parse_currency_input(raw: str) -> Decimal:
    """Interpreta entrada pt-BR ou número com ponto decimal (ex.: resposta da API em string)."""
    cleaned = strip_currency_decorations(raw)
    if not cleaned:
        return Decimal("0.00")

    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
        return _quantize_positive(cleaned)

    if "." in cleaned:
        parts = cleaned.split(".")
        last = parts[-1] if parts else ""
        is_decimal_dot = len(parts) == 2 and bool(last) and len(last) <= 2
        if is_decimal_dot:
            return _quantize_positive(cleaned)
        cleaned = cleaned.replace(".", "")
        return _quantize_positive(cleaned)

    digits = re.sub(r"\D", "", cleaned)
    if not digits:
        return Decimal("0.00")
    return _quantize_positive(digits)


def _quantize_positive(value: str) -> Decimal:
    try:
        d = Decimal(value)
    except InvalidOperation:
        return Decimal("0.00")
    if d < 0:
        return Decimal("0.00")
    return d.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)


def round_money(value: Decimal | float | int) -> Decimal:
    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation:
        return Decimal("0.00")
    return d.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)


def normalize_money(value: str | float | int | Decimal | None) -> Decimal:
    """Aceita valor da API (número) ou texto da UI; retorna Decimal com 2 casas."""
    if value is None or value == "":
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return round_money(value)
    if isinstance(value, (int, float)):
        return round_money(value)
    return parse_currency_input(str(value))


def money_to_float(value: Decimal) -> float:
    return float(round_money(value))
