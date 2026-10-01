from __future__ import annotations

import io
from datetime import date, datetime, timezone
from typing import Any, Sequence
from xml.sax.saxutils import escape

from app.services.export.xlsx_table import SheetSpec, build_workbook_bytes
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def format_brl(n: float | int | None) -> str:
    if n is None:
        return ""
    try:
        v = float(n)
    except (TypeError, ValueError):
        return str(n)
    return _brl_py(v)


def _brl_py(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_date_br(d: date | datetime | str | None) -> str:
    if d is None:
        return ""
    if isinstance(d, str):
        if len(d) >= 10 and d[4] == "-":
            y, m, dd = d[:10].split("-")
            return f"{dd}/{m}/{y}"
        return d
    if isinstance(d, datetime):
        d = d.date()
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def build_xlsx_bytes(
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    sheet_title: str = "Exportação",
    totals_row: Sequence[Any] | None = None,
) -> bytes:
    """Relatórios que montam as células como TEXTO formatado ("R$ 1.234,56", "dd/mm/aaaa").

    Sai no padrão único (`xlsx_table`): o texto é convertido em número/data, e as colunas de
    valor ganham total por SUBTOTAL. Com `totals_row`, o total informado é respeitado: vira
    SUBTOTAL quando é a soma da coluna, senão fica como valor fixo.
    """
    spec = SheetSpec(
        title=sheet_title, headers=headers, rows=rows, parse_text=True, auto_totals=totals_row is None
    )
    if totals_row is not None:
        spec.totals = _legacy_totals(headers, rows, totals_row)
    return build_workbook_bytes([spec])


def _legacy_totals(
    headers: Sequence[str], rows: Sequence[Sequence[Any]], totals_row: Sequence[Any]
) -> dict[int, Any]:
    from app.services.export.xlsx_table import _parse_one

    def num(v: Any) -> float | None:
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            kind, parsed = _parse_one(v.strip())
            return parsed if kind in ("money", "percent") else None
        return None

    out: dict[int, Any] = {}
    for c, total in enumerate(totals_row, start=1):
        if c == 1:
            continue
        t = num(total)
        if t is None:
            continue
        col_sum = sum(num(r[c - 1]) or 0.0 for r in rows if len(r) >= c)
        out[c] = "sum" if abs(col_sum - t) < 0.005 else t
    return out


def build_table_xlsx_bytes(
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    sheet_title: str = "Relatório",
    money_columns: frozenset[int] = frozenset(),
    date_columns: frozenset[int] = frozenset(),
    percent_columns: frozenset[int] = frozenset(),
    totals: dict[int, str] | None = None,
    total_label: str = "Total",
    bold_columns: frozenset[int] = frozenset(),
    freeze: str = "B2",
) -> bytes:
    """Uma aba no padrão único com totais explícitos ({coluna: "sum" | "count"})."""
    return build_workbook_bytes([SheetSpec(
        title=sheet_title, headers=headers, rows=rows, money_columns=money_columns,
        date_columns=date_columns, percent_columns=percent_columns,
        totals=dict(totals or {}), total_label=total_label,
        bold_columns=bold_columns, freeze=freeze,
    )])


def build_multisheet_operational_xlsx_bytes(sheets: Sequence[dict[str, Any]]) -> bytes:
    """Várias abas no padrão único (uma Tabela por aba).

    Cada `sheet` = {"title", "headers", "rows", "money_columns"?, "date_columns"?,
    "totals"?: bool | {coluna: "sum"}}. `totals` padrão = soma de todas as colunas de valor;
    False para abas em que somar não faz sentido (indicadores, saldos acumulados).
    """
    return build_workbook_bytes([
        _operational_spec(
            title=str(spec.get("title") or f"Aba {i + 1}"),
            headers=spec.get("headers") or [],
            rows=spec.get("rows") or [],
            money_columns=spec.get("money_columns"),
            date_columns=spec.get("date_columns"),
            totals=spec.get("totals", True),
        )
        for i, spec in enumerate(sheets)
    ])


def _operational_spec(
    *, title, headers, rows, money_columns, date_columns, totals: bool | dict[int, str]
) -> SheetSpec:
    money = frozenset(money_columns or ())
    if isinstance(totals, dict):
        total_map = dict(totals)
    else:
        total_map = {c: "sum" for c in money if c != 1} if totals else {}
    return SheetSpec(
        title=title,
        headers=headers,
        rows=rows,
        money_columns=money,
        date_columns=frozenset(date_columns or ()),
        totals=total_map,
        # Datas chegam como texto "dd/mm/aaaa" em alguns relatórios: vira data de verdade.
        parse_text=True,
    )


def _pdf_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.drawString(1.5 * cm, 0.8 * cm, "SGC")
    page = canvas.getPageNumber()
    canvas.drawRightString(doc.pagesize[0] - 1.5 * cm, 0.8 * cm, f"Página {page}")
    canvas.restoreState()


def build_executive_pdf_bytes(
    *,
    title: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    meta_lines: Sequence[str],
    totals_row: Sequence[Any] | None = None,
) -> bytes:
    """PDF executivo com marca SGC, metadados e paginação."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        rightMargin=1.2 * cm,
        leftMargin=1.2 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.4 * cm,
    )
    styles = getSampleStyleSheet()
    story: list[Any] = []
    story.append(Paragraph("<b>SGC</b>", styles["Normal"]))
    story.append(Paragraph(f"<b>{escape(title)}</b>", styles["Title"]))
    gen = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    story.append(Paragraph(f"Gerado em: {gen}", styles["Normal"]))
    for line in meta_lines:
        if line:
            story.append(Paragraph(escape(line), styles["Normal"]))
    story.append(Spacer(1, 0.35 * cm))

    data: list[list[Any]] = [list(headers)]
    for row in rows:
        data.append([("" if v is None else str(v)) for v in row])
    if totals_row is not None:
        data.append([("" if v is None else str(v)) for v in totals_row])

    col_count = max(len(r) for r in data) if data else 1
    w = doc.width / max(col_count, 1)
    tbl = Table(data, colWidths=[w] * col_count, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    if totals_row is not None:
        last = len(data) - 1
        tbl.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, last), (-1, last), "Helvetica-Bold"),
                    ("BACKGROUND", (0, last), (-1, last), colors.HexColor("#f8fafc")),
                ]
            )
        )
    story.append(tbl)
    doc.build(story, onFirstPage=_pdf_footer, onLaterPages=_pdf_footer)
    buf.seek(0)
    return buf.getvalue()


def build_pdf_bytes(
    *,
    title: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    meta_lines: Sequence[str],
    totals_row: Sequence[Any] | None = None,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
    )
    styles = getSampleStyleSheet()
    story: list[Any] = []
    story.append(Paragraph(f"<b>{escape(title)}</b>", styles["Title"]))
    gen = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    story.append(Paragraph(f"Gerado em: {gen}", styles["Normal"]))
    for line in meta_lines:
        if line:
            story.append(Paragraph(escape(line), styles["Normal"]))
    story.append(Spacer(1, 0.4 * cm))

    data: list[list[Any]] = [list(headers)]
    for row in rows:
        data.append([("" if v is None else str(v)) for v in row])
    if totals_row is not None:
        data.append([("" if v is None else str(v)) for v in totals_row])

    col_count = max(len(r) for r in data) if data else 1
    w = doc.width / max(col_count, 1)
    tbl = Table(data, colWidths=[w] * col_count, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    if totals_row is not None:
        last = len(data) - 1
        tbl.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, last), (-1, last), "Helvetica-Bold"),
                    ("BACKGROUND", (0, last), (-1, last), colors.HexColor("#f8fafc")),
                ]
            )
        )
    story.append(tbl)
    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


def export_filename(module_slug: str, ext: str, period_suffix: str | None = None) -> str:
    suf = period_suffix or datetime.now(timezone.utc).strftime("%Y-%m")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in module_slug)
    return f"{safe}_{suf}.{ext}"


def build_projects_summary_xlsx_bytes(
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    totals_row: Sequence[Any],
) -> bytes:
    """Resumo por projeto: valores em R$, última coluna = margem (%), negativos em vermelho."""
    ncols = len(headers)
    margin_col = ncols
    money = frozenset(range(2, margin_col))
    totals: dict[int, Any] = {}
    for c, val in enumerate(totals_row, start=1):
        if c == 1 or not isinstance(val, (int, float)):
            continue
        if c == margin_col:
            totals[c] = float(val)  # margem do total não é soma das margens
            continue
        col_sum = sum(float(r[c - 1]) for r in rows if len(r) >= c and isinstance(r[c - 1], (int, float)))
        totals[c] = "sum" if abs(col_sum - float(val)) < 0.005 else float(val)
    return build_workbook_bytes([SheetSpec(
        title="Resumo por projeto",
        headers=headers,
        rows=rows,
        money_columns=money,
        percent_columns=frozenset({margin_col}),
        totals=totals,
        negative_red=True,
    )])


def build_projects_summary_pdf_bytes(
    *,
    title: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    meta_lines: Sequence[str],
    totals_row: Sequence[Any],
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        rightMargin=1.2 * cm,
        leftMargin=1.2 * cm,
        topMargin=1.0 * cm,
        bottomMargin=1.0 * cm,
    )
    styles = getSampleStyleSheet()
    story: list[Any] = []
    story.append(Paragraph(f"<b>{escape(title)}</b>", styles["Title"]))
    gen = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    story.append(Paragraph(f"Gerado em: {gen}", styles["Normal"]))
    for line in meta_lines:
        if line:
            story.append(Paragraph(escape(line), styles["Normal"]))
    story.append(Spacer(1, 0.35 * cm))

    data: list[list[Any]] = [list(headers)]
    for row in rows:
        data.append([("" if v is None else str(v)) for v in row])
    data.append([("" if v is None else str(v)) for v in totals_row])

    col_count = max(len(r) for r in data) if data else 1
    w = doc.width / max(col_count, 1)
    tbl = Table(data, colWidths=[w] * col_count, repeatRows=1)
    yellow = colors.HexColor("#FFFF00")
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), yellow),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    last = len(data) - 1
    tbl.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, last), (-1, last), "Helvetica-Bold"),
                ("BACKGROUND", (0, last), (-1, last), yellow),
            ]
        )
    )
    story.append(tbl)
    doc.build(story)
    buf.seek(0)
    return buf.getvalue()
