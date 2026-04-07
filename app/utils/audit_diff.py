"""Diff estruturado para auditoria: apenas campos alterados, formato field_changes."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import Any
from uuid import UUID


# Campos que não devem aparecer em auditoria (ruído ou sensíveis em log estruturado)
AUDIT_IGNORE_KEYS: frozenset[str] = frozenset(
    {
        "updated_at",
        "created_at",
        "password_hash",
        "password",
    }
)


def _normalize_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, float):
        return round(value, 10) if value != round(value, 6) else round(value, 6)
    if isinstance(value, PyEnum):
        return value.value
    return value


def _normalize_for_compare(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _normalize_for_compare(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_normalize_for_compare(v) for v in value]
    return _normalize_scalar(value)


def _values_equal(a: Any, b: Any) -> bool:
    return _normalize_for_compare(a) == _normalize_for_compare(b)


def generate_diff(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    *,
    ignore_keys: frozenset[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Monta field_changes no formato obrigatório:
    { "campo": { "before": ..., "after": ... } }

    Regras:
    - Somente chaves presentes em ambos (update) ou em um dos lados (create/delete parcial).
    - Ignora chaves em AUDIT_IGNORE_KEYS (ou ignore_keys).
    - Se before e after forem None → {}.
    - Fallback: create (before is None) → cada campo em after com before=None.
    - Fallback: delete (after is None) → cada campo em before com after=None.
    """
    ignore = ignore_keys if ignore_keys is not None else AUDIT_IGNORE_KEYS

    if before is None and after is None:
        return {}

    if before is None and after is not None:
        out: dict[str, dict[str, Any]] = {}
        for k, v in after.items():
            if k in ignore:
                continue
            out[k] = {"before": None, "after": _normalize_scalar(v)}
        return out

    if before is not None and after is None:
        out = {}
        for k, v in before.items():
            if k in ignore:
                continue
            out[k] = {"before": _normalize_scalar(v), "after": None}
        return out

    assert before is not None and after is not None
    keys = set(before.keys()) | set(after.keys())
    out = {}
    for k in sorted(keys):
        if k in ignore:
            continue
        b = before.get(k)
        a = after.get(k)
        if k not in before:
            out[k] = {"before": None, "after": _normalize_scalar(a)}
            continue
        if k not in after:
            out[k] = {"before": _normalize_scalar(b), "after": None}
            continue
        if _values_equal(b, a):
            continue
        out[k] = {"before": _normalize_scalar(b), "after": _normalize_scalar(a)}
    return out
