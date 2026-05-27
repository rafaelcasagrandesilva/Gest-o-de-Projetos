from __future__ import annotations

from sqlalchemy import ColumnElement, func, not_, or_

MACRO_CATEGORY_EPI = "EPI"

ASSET_MACRO_CATEGORIES: list[str] = [
    "Tecnologia",
    "EPI",
    "EPC",
    "Ferramenta",
    "Operacional",
    "Instrumentação",
    "Veículos",
    "Uniformes",
]

_LEGACY_TO_MACRO: dict[str, str] = {
    "TECNOLOGIA": "Tecnologia",
    "EPIS": "EPI",
    "EPI": "EPI",
    "EPC": "EPC",
    "FERRAMENTAS": "Ferramenta",
    "FERRAMENTA": "Ferramenta",
    "OPERACIONAL": "Operacional",
    "INSTRUMENTACAO": "Instrumentação",
    "INSTRUMENTAÇÃO": "Instrumentação",
    "VEICULOS": "Veículos",
    "VEÍCULOS": "Veículos",
    "UNIFORMES": "Uniformes",
    "UNIFORME": "Uniformes",
    "VESTIMENTAS": "Uniformes",
    "VESTIMENTAS OPERACIONAIS": "Uniformes",
}

_SIZE_MACRO_CATEGORIES = frozenset({"EPI", "EPC", "Uniformes"})

PATRIMONIAL_MACRO_CATEGORIES: list[str] = [c for c in ASSET_MACRO_CATEGORIES if c != MACRO_CATEGORY_EPI]


def is_epi_category(category: str | None) -> bool:
    return normalize_macro_category(category) == MACRO_CATEGORY_EPI


def epi_category_db_values() -> frozenset[str]:
    """Valores possíveis de `assets.category` que representam EPI (inclui legado)."""
    vals: set[str] = {MACRO_CATEGORY_EPI}
    for leg, macro in _LEGACY_TO_MACRO.items():
        if macro == MACRO_CATEGORY_EPI:
            vals.add(leg)
            vals.add(macro)
    for macro in ASSET_MACRO_CATEGORIES:
        if normalize_macro_category(macro) == MACRO_CATEGORY_EPI:
            vals.add(macro)
    return frozenset(vals)


def sqlalchemy_is_epi_category(column) -> ColumnElement[bool]:
    """Predicado SQL: linha é categoria EPI (case-insensitive, trim)."""
    normalized = func.upper(func.trim(column))
    return or_(*(normalized == v.upper() for v in epi_category_db_values()))


def sqlalchemy_exclude_epi(column) -> ColumnElement[bool]:
    return not_(sqlalchemy_is_epi_category(column))


def categories_for_scope(scope: str | None) -> list[str]:
    if scope == "epi":
        return [MACRO_CATEGORY_EPI]
    if scope == "patrimonial":
        return list(PATRIMONIAL_MACRO_CATEGORIES)
    return list(ASSET_MACRO_CATEGORIES)


def normalize_macro_category(category: str | None) -> str:
    raw = (category or "").strip()
    if not raw:
        return "Operacional"
    mapped = _LEGACY_TO_MACRO.get(raw.upper())
    if mapped:
        return mapped
    for macro in ASSET_MACRO_CATEGORIES:
        if raw.casefold() == macro.casefold():
            return macro
    return raw


def macro_category_supports_size(category: str | None) -> bool:
    return normalize_macro_category(category) in _SIZE_MACRO_CATEGORIES


def normalize_tags(tags: list[str] | str | None) -> list[str] | None:
    if tags is None:
        return None
    if isinstance(tags, str):
        parts = tags.replace(";", ",").split(",")
    else:
        parts = list(tags)
    out: list[str] = []
    for part in parts:
        tag = str(part).strip().lower()
        if not tag or tag in out or len(tag) > 48:
            continue
        out.append(tag)
    return out or None
