from __future__ import annotations

from typing import Any

from app.services.payable_import.constants import LEGACY_HEADER_HINTS, MAX_IMPORT_ROWS
from app.services.payable_import.file_reader import RawSheet, read_raw_sheet
from app.services.payable_import.mapping import ColumnMapping, parse_mapped_row
from app.services.payable_import.normalization import cell_str


def _is_legacy_header_row(values: tuple[Any, ...]) -> bool:
    joined = " ".join(cell_str(v).casefold() for v in values[:8] if v is not None)
    return any(h in joined for h in LEGACY_HEADER_HINTS)


def looks_like_legacy_template(raw: RawSheet) -> bool:
    for line_no, row in raw.rows[:3]:
        if _is_legacy_header_row(row):
            return True
    return False


def parse_legacy_workbook(content: bytes, *, filename: str = "") -> list[tuple[int, tuple[Any, ...]]]:
    """Compatibilidade: colunas fixas A–F (índices 0–5)."""
    raw = read_raw_sheet(content=content, filename=filename)
    out: list[tuple[int, tuple[Any, ...]]] = []
    for idx, row in raw.rows:
        if idx == 1 and _is_legacy_header_row(row):
            continue
        if not any(cell_str(v) for v in (row[:6] if len(row) >= 6 else row)):
            continue
        out.append((idx, row))
        if len(out) > MAX_IMPORT_ROWS:
            raise ValueError(f"Planilha excede o limite de {MAX_IMPORT_ROWS} linhas de dados.")
    return out


def legacy_mapping() -> ColumnMapping:
    """Mapeamento por índice simulado via nomes artificiais na linha de cabeçalho legada."""
    return ColumnMapping(
        cost_center="__col_0__",
        name="__col_1__",
        due_date="__col_2__",
        amount="__col_3__",
        observation="__col_4__",
        category="__col_5__",
    )


def legacy_row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    cells = list(row) + [None] * max(0, 6 - len(row))
    return {
        "__col_0__": cells[0],
        "__col_1__": cells[1],
        "__col_2__": cells[2],
        "__col_3__": cells[3],
        "__col_4__": cells[4],
        "__col_5__": cells[5],
    }


def parse_legacy_data_row(line_number: int, row: tuple[Any, ...]):
    return parse_mapped_row(
        line_number=line_number,
        row=legacy_row_to_dict(row),
        mapping=legacy_mapping(),
    )
