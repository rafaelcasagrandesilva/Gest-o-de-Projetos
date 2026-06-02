"""Utilitários para flag include_in_dashboard e auditoria de alterações."""

from __future__ import annotations

from typing import Callable

DASHBOARD_INCLUSION_LOG_PREFIX = "Dashboard Financeiro:"


def dashboard_inclusion_label(value: bool) -> str:
    return "SIM" if value else "NÃO"


def format_dashboard_inclusion_change(*, before: bool, after: bool) -> str:
    return (
        f"{DASHBOARD_INCLUSION_LOG_PREFIX} participação alterada de "
        f"{dashboard_inclusion_label(before)} para {dashboard_inclusion_label(after)}."
    )


def append_observation_line(existing: str | None, line: str) -> str:
    line = line.strip()
    if not line:
        return (existing or "").strip()
    prev = (existing or "").strip()
    return f"{prev}\n{line}".strip() if prev else line


def apply_dashboard_inclusion_change(
    *,
    before: bool,
    after: bool | None,
    set_value: Callable[[bool], None],
    append_line: Callable[[str], None],
) -> None:
    if after is None or after == before:
        return
    set_value(bool(after))
    append_line(format_dashboard_inclusion_change(before=before, after=bool(after)))
