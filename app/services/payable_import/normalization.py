from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.payable_import.constants import DEFAULT_CATEGORY


def cell_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def normalize_text(value: Any) -> str:
    return " ".join(cell_str(value).split())


def parse_amount(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            amt = Decimal(str(value))
        except InvalidOperation:
            return None
        if amt <= 0:
            return None
        return amt.quantize(Decimal("0.01"))
    raw = cell_str(value)
    if not raw:
        return None
    cleaned = raw.replace("R$", "").replace(" ", "")
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    try:
        amt = Decimal(cleaned)
    except InvalidOperation:
        return None
    if amt <= 0:
        return None
    return amt.quantize(Decimal("0.01"))


def parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = cell_str(value)
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", raw)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    return None


def default_category(raw: str | None) -> str:
    cat = normalize_text(raw or "")
    return (cat[:120] if cat else DEFAULT_CATEGORY)
