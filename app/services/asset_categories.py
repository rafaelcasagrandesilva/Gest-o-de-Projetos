from __future__ import annotations

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
