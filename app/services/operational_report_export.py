from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Sequence

from app.services.export.builders import (
    build_executive_pdf_bytes,
    build_operational_xlsx_bytes,
    export_filename,
    format_brl,
    format_date_br,
)

MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MIME_PDF = "application/pdf"

_OPERATIONAL_SPECS: dict[str, tuple[list[str], list[str], frozenset[int]]] = {
    "payables_detailed": (
        [
            "Vencimento",
            "Competência",
            "Nome",
            "Projeto",
            "Categoria",
            "Tipo",
            "Valor original",
            "Valor pago",
            "Saldo",
            "Status",
            "Observações",
        ],
        [
            "vencimento",
            "competencia",
            "nome",
            "projeto",
            "categoria",
            "tipo",
            "valor_original",
            "valor_pago",
            "saldo",
            "status",
            "observacoes",
        ],
        frozenset({7, 8, 9}),
    ),
    "receivables_detailed": (
        ["Cliente", "Projeto", "NF", "Emissão", "Vencimento", "Valor", "Recebido", "Saldo", "Status"],
        ["cliente", "projeto", "nf", "emissao", "vencimento", "valor", "recebido", "saldo", "status"],
        frozenset({6, 7, 8}),
    ),
    "invoices_detailed": (
        ["Nº NF", "Cliente", "Projeto", "Emissão", "Vencimento", "Valor", "Recebido", "Saldo", "Status"],
        ["numero_nf", "cliente", "projeto", "emissao", "vencimento", "valor", "recebido", "saldo", "status"],
        frozenset({6, 7, 8}),
    ),
    "assets_inventory": (
        [
            "Código",
            "Item",
            "Categoria",
            "Tamanho",
            "Responsável",
            "Centro de custo",
            "Status",
            "Estado físico",
            "Valor",
            "Tags",
            "CA",
            "Nº série",
            "Observações",
        ],
        [
            "codigo",
            "item",
            "categoria",
            "tamanho",
            "responsavel",
            "centro_custo",
            "status",
            "estado_fisico",
            "valor",
            "tags",
            "ca",
            "numero_serie",
            "observacoes",
        ],
        frozenset({9}),
    ),
    "assets_in_use": (
        ["Código", "Item", "Responsável", "Data entrega", "Estado físico", "Centro de custo", "Valor"],
        ["codigo", "item", "responsavel", "data_entrega", "estado_fisico", "centro_custo", "valor"],
        frozenset({7}),
    ),
    "assets_inspections": (
        ["Ativo", "Tipo inspeção", "Validade", "Status validade", "Dias restantes", "Responsável", "Alerta"],
        ["ativo", "tipo_inspecao", "validade", "status_validade", "dias_restantes", "responsavel", "alerta"],
        frozenset(),
    ),
    "assets_movements": (
        [
            "Ativo",
            "Entregador",
            "Recebedor",
            "Data entrega",
            "Data devolução",
            "Resp. devolução",
            "Estado devolução",
            "Observações",
        ],
        [
            "ativo",
            "entregador",
            "recebedor",
            "data_entrega",
            "data_devolucao",
            "responsavel_devolucao",
            "estado_devolucao",
            "observacoes",
        ],
        frozenset(),
    ),
}


def _meta_from_filters(filters: dict[str, Any]) -> list[str]:
    if not filters:
        return []
    parts = []
    for k, v in filters.items():
        if v is None or v == "":
            continue
        parts.append(f"{k}={v}")
    return [f"Filtros: {'; '.join(parts)}"] if parts else []


def _row_values(
    row: dict[str, Any],
    keys: list[str],
    money_cols: frozenset[int],
) -> list[Any]:
    out: list[Any] = []
    for idx, key in enumerate(keys, start=1):
        val = row.get(key)
        if idx in money_cols and isinstance(val, (int, float)):
            out.append(float(val))
        elif key in ("vencimento", "emissao", "data_entrega", "data_devolucao", "validade") and val:
            out.append(format_date_br(str(val)[:10]))
        else:
            out.append("" if val is None else val)
    return out


def render_operational_report_bytes(
    report_type: str, payload: dict[str, Any], fmt: str
) -> tuple[bytes, str, str]:
    if fmt not in ("xlsx", "pdf"):
        raise ValueError("formato inválido")
    spec = _OPERATIONAL_SPECS.get(report_type)
    if not spec:
        raise ValueError(f"tipo operacional desconhecido: {report_type}")
    headers, keys, money_cols = spec
    raw_rows = payload.get("rows") or []
    xlsx_rows = [_row_values(r, keys, money_cols) for r in raw_rows]
    pdf_rows = []
    for r in raw_rows:
        pdf_row = []
        for idx, key in enumerate(keys, start=1):
            val = r.get(key)
            if idx in money_cols and isinstance(val, (int, float)):
                pdf_row.append(format_brl(val))
            elif key in ("vencimento", "emissao", "data_entrega", "data_devolucao", "validade") and val:
                pdf_row.append(format_date_br(str(val)[:10]))
            else:
                pdf_row.append("" if val is None else str(val))
        pdf_rows.append(pdf_row)

    title = str(payload.get("title") or report_type)
    meta = _meta_from_filters(payload.get("filters") or {})
    meta.insert(0, f"Registros: {len(raw_rows)}")
    suffix = datetime.now(timezone.utc).strftime("%Y-%m")
    slug = report_type

    if fmt == "xlsx":
        raw = build_operational_xlsx_bytes(
            headers=headers,
            rows=xlsx_rows,
            sheet_title=title[:31],
            money_columns=money_cols,
        )
        return raw, export_filename(slug, "xlsx", suffix), MIME_XLSX

    raw = build_executive_pdf_bytes(title=title, headers=headers, rows=pdf_rows, meta_lines=meta)
    return raw, export_filename(slug, "pdf", suffix), MIME_PDF
