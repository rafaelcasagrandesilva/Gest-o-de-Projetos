from __future__ import annotations

import io
from datetime import date, datetime, timezone
from typing import Any, Sequence
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.filters import AutoFilter
from openpyxl.worksheet.table import Table as XlTable
from openpyxl.worksheet.table import TableColumn, TableStyleInfo
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
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title[:31]
    header_font = Font(bold=True)
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=str(h))
        cell.font = header_font
        cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    for r_idx, row in enumerate(rows, start=2):
        for c_idx, val in enumerate(row, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=val)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    if totals_row is not None:
        r = len(rows) + 3
        for c_idx, val in enumerate(totals_row, start=1):
            cell = ws.cell(row=r, column=c_idx, value=val)
            cell.font = Font(bold=True)
    for col in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 18
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


_ROW_HEIGHT = 15
_THIN_SIDE = Side(style="thin", color="BFC7D1")
_THIN_BORDER = Border(left=_THIN_SIDE, right=_THIN_SIDE, top=_THIN_SIDE, bottom=_THIN_SIDE)


def _write_operational_sheet(
    ws,
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    money_columns: frozenset[int] | None = None,
    date_columns: frozenset[int] | None = None,
    polished: bool = False,
) -> None:
    """Escreve UMA planilha operacional (cabeçalho, autofiltro, largura auto, formatos) em `ws`.

    Corpo compartilhado por `build_operational_xlsx_bytes` (aba única) e
    `build_multisheet_operational_xlsx_bytes` (várias abas) — mesma aparência/formatação.

    `polished=True` entrega a planilha pronta para leitura: cabeçalho centralizado, linha 1
    congelada, grade do Excel desligada e borda fina em cada célula (só as linhas da tabela).
    Opt-in para não mudar a cara dos relatórios que já circulam."""
    header_fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
    ncols = len(headers)
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=str(h))
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(
            horizontal="center" if polished else "left", vertical="center", wrap_text=True
        )
        if polished:
            cell.border = _THIN_BORDER
    for r_idx, row in enumerate(rows, start=2):
        for c_idx, val in enumerate(row, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=val)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if polished:
                cell.border = _THIN_BORDER
            if money_columns and c_idx in money_columns and isinstance(val, (int, float)):
                cell.number_format = _BRL_NUM_FMT
            if date_columns and c_idx in date_columns and val not in (None, ""):
                cell.number_format = "DD/MM/YYYY"
    last_row = max(1, len(rows) + 1)
    if ncols and last_row:
        ws.auto_filter.ref = f"A1:{get_column_letter(ncols)}{last_row}"
    for col in range(1, ncols + 1):
        max_len = len(str(headers[col - 1]))
        for r_idx in range(2, last_row + 1):
            v = ws.cell(row=r_idx, column=col).value
            if v is not None:
                max_len = max(max_len, min(len(str(v)), 48))
        ws.column_dimensions[get_column_letter(col)].width = min(max(max_len + 2, 12), 42)
    if polished:
        ws.freeze_panes = "A2"
        ws.sheet_view.showGridLines = False
        ws.row_dimensions[1].height = 30
        # Altura FIXA de uma linha em todas as linhas de dados: a tabela fica uniforme e a
        # quebra de texto não estica a linha (um andamento de 4 mil caracteres viraria uma linha
        # de tela cheia). O texto segue completo na célula — clique para ler na barra de fórmulas.
        for r_idx in range(2, last_row + 1):
            ws.row_dimensions[r_idx].height = _ROW_HEIGHT


# Formato "Contábil" do Excel em R$ (o mesmo que o usuário aplica à mão): zero aparece como "-".
_ACCOUNTING_BRL_FMT = '_-"R$"\\ * #,##0.00_-;\\-"R$"\\ * #,##0.00_-;_-"R$"\\ * "-"??_-;_-@_-'
_TABLE_HEADER_FILL = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
# Funções da linha de total da Tabela do Excel → código do SUBTOTAL (ignora linhas filtradas).
_SUBTOTAL_CODES = {"sum": 109, "count": 103}


def build_table_xlsx_bytes(
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    sheet_title: str = "Relatório",
    money_columns: frozenset[int] = frozenset(),
    date_columns: frozenset[int] = frozenset(),
    totals: dict[int, str] | None = None,
    total_label: str = "Total",
    bold_columns: frozenset[int] = frozenset(),
    freeze: str = "B2",
) -> bytes:
    """Planilha pronta para uso: os dados viram uma TABELA do Excel.

    - valores são NÚMEROS no formato Contábil R$ (nada de texto "R$ 1.234,56", que o Excel
      marca com o triângulo verde e não soma);
    - datas são datas de verdade (DD/MM/AAAA), que ordenam e filtram;
    - linha de total da Tabela com SUBTOTAL — a soma acompanha o filtro;
    - cabeçalho amarelo centralizado, borda fina, linha 1 e coluna A congeladas, sem grade,
      SEM quebra de texto (todas as linhas com a mesma altura).

    Colunas são 1-based. `totals` = {coluna: "sum" | "count"}; a 1ª coluna recebe `total_label`.
    """
    totals = dict(totals or {})
    thin = Side(style="thin")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title[:31]
    ncols = len(headers)
    names = _unique_headers(headers)

    for c, h in enumerate(names, start=1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.font = Font(bold=True)
        cell.fill = _TABLE_HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border

    for r_idx, row in enumerate(rows, start=2):
        for c_idx, val in enumerate(row, start=1):
            if c_idx in date_columns:
                val = _as_date(val)
            cell = ws.cell(row=r_idx, column=c_idx, value=val)
            cell.alignment = Alignment(vertical="top")
            cell.border = border
            if c_idx in money_columns:
                cell.number_format = _ACCOUNTING_BRL_FMT
            elif c_idx in date_columns and val is not None:
                cell.number_format = "DD/MM/YYYY"
            if c_idx in bold_columns:
                cell.font = Font(bold=True)

    last_data = len(rows) + 1
    total_row = last_data + 1
    table_name = "Tabela1"
    columns: list[TableColumn] = []
    for c, name in enumerate(names, start=1):
        col = TableColumn(id=c, name=name)
        func = totals.get(c)
        cell = ws.cell(row=total_row, column=c)
        cell.border = border
        if c == 1 and func is None:
            col.totalsRowLabel = total_label
            cell.value = total_label
        elif func in _SUBTOTAL_CODES:
            col.totalsRowFunction = func
            cell.value = f"=SUBTOTAL({_SUBTOTAL_CODES[func]},{table_name}[{_table_ref(name)}])"
        if c in money_columns:
            cell.number_format = _ACCOUNTING_BRL_FMT
        if c in bold_columns:
            cell.font = Font(bold=True)
        columns.append(col)

    if ncols:
        table = XlTable(
            displayName=table_name,
            ref=f"A1:{get_column_letter(ncols)}{total_row}",
            totalsRowCount=1,
        )
        table.tableColumns = columns
        table.tableStyleInfo = TableStyleInfo(name="TableStyleLight16", showRowStripes=True)
        # Linha de total fora do autofiltro da tabela (senão o filtro a esconderia).
        table.autoFilter = AutoFilter(ref=f"A1:{get_column_letter(ncols)}{last_data}")
        ws.add_table(table)

    for c in range(1, ncols + 1):
        longest = len(str(names[c - 1])) + 4  # espaço da seta do filtro
        for r_idx in range(2, last_data + 1):
            v = ws.cell(row=r_idx, column=c).value
            if v is None:
                continue
            text = format_brl(v) if c in money_columns and isinstance(v, (int, float)) else str(v)
            longest = max(longest, min(len(text), 50))
        ws.column_dimensions[get_column_letter(c)].width = min(max(longest + 2, 10), 52)

    ws.freeze_panes = freeze
    ws.sheet_view.showGridLines = False
    # Fórmulas do total saem sem valor em cache: o Excel recalcula ao abrir.
    wb.calculation.fullCalcOnLoad = True
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def _unique_headers(headers: Sequence[str]) -> list[str]:
    """Nomes de coluna de Tabela do Excel precisam ser únicos e não vazios."""
    seen: dict[str, int] = {}
    out: list[str] = []
    for i, h in enumerate(headers, start=1):
        name = str(h).strip() or f"Coluna{i}"
        if name.lower() in seen:
            seen[name.lower()] += 1
            name = f"{name}{seen[name.lower()]}"
        else:
            seen[name.lower()] = 1
        out.append(name)
    return out


def _table_ref(name: str) -> str:
    """Escapa o nome da coluna para referência estruturada (Tabela1[Coluna])."""
    return "".join(f"'{ch}" if ch in "[]#'" else ch for ch in name)


def _as_date(val: Any) -> Any:
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date) or val in (None, ""):
        return val if val != "" else None
    text = str(val).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return val


def build_operational_xlsx_bytes(
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    sheet_title: str = "Relatório",
    money_columns: frozenset[int] | None = None,
    date_columns: frozenset[int] | None = None,
) -> bytes:
    """Planilha operacional: cabeçalho, autofiltro, largura automática e formatos básicos."""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title[:31]
    _write_operational_sheet(
        ws, headers=headers, rows=rows, money_columns=money_columns, date_columns=date_columns
    )
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def build_multisheet_operational_xlsx_bytes(sheets: Sequence[dict[str, Any]]) -> bytes:
    """Workbook operacional com VÁRIAS abas (mesma formatação por aba do builder de aba única).

    Cada `sheet` = {"title": str, "headers": [...], "rows": [[...]],
    "money_columns": frozenset[int]?, "date_columns": frozenset[int]?,
    "polished": bool?}. A ordem da lista é a
    ordem das abas. Títulos são truncados em 31 chars (limite do openpyxl)."""
    wb = Workbook()
    for i, spec in enumerate(sheets):
        ws = wb.active if i == 0 else wb.create_sheet()
        ws.title = str(spec.get("title") or f"Aba {i + 1}")[:31]
        _write_operational_sheet(
            ws,
            headers=spec.get("headers") or [],
            rows=spec.get("rows") or [],
            money_columns=spec.get("money_columns"),
            date_columns=spec.get("date_columns"),
            polished=bool(spec.get("polished")),
        )
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


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


_YELLOW = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
_BRL_NUM_FMT = '[$R$-416] #,##0.00'
_PCT_NUM_FMT = "0.00%"


def _apply_negative_red(cell) -> None:
    v = cell.value
    if isinstance(v, (int, float)) and v < 0:
        cell.font = Font(color="FF0000")


def build_projects_summary_xlsx_bytes(
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    totals_row: Sequence[Any],
) -> bytes:
    """Planilha executiva: cabeçalho amarelo, totais amarelos, negativos em vermelho; valores numéricos em moeda."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Resumo por projeto"[:31]
    ncols = len(headers)
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=str(h))
        cell.font = Font(bold=True)
        cell.fill = _YELLOW
        cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    margin_col = ncols
    for r_idx, row in enumerate(rows, start=2):
        for c_idx, val in enumerate(row, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=val)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if c_idx == 1:
                continue
            if c_idx == margin_col:
                if isinstance(val, (int, float)):
                    cell.number_format = _PCT_NUM_FMT
                    cell.value = float(val)
                _apply_negative_red(cell)
            else:
                if isinstance(val, (int, float)):
                    cell.number_format = _BRL_NUM_FMT
                    cell.value = float(val)
                _apply_negative_red(cell)
    tr = len(rows) + 2
    for c_idx, val in enumerate(totals_row, start=1):
        cell = ws.cell(row=tr, column=c_idx, value=val)
        is_neg = isinstance(val, (int, float)) and val < 0
        cell.font = Font(bold=True, color="FF0000") if is_neg else Font(bold=True)
        cell.fill = _YELLOW
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        if c_idx == 1:
            continue
        if c_idx == margin_col:
            if isinstance(val, (int, float)):
                cell.number_format = _PCT_NUM_FMT
                cell.value = float(val)
        else:
            if isinstance(val, (int, float)):
                cell.number_format = _BRL_NUM_FMT
                cell.value = float(val)
    for col in range(1, ncols + 1):
        ws.column_dimensions[get_column_letter(col)].width = 16
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


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
