"""Exportação do relatório do Jurídico (Excel multi-aba e PDF executivo).

Reusa os builders compartilhados (`export/builders.py`) e a nomenclatura/cabeçalho de identificação
(`export/report_meta.py`), então o arquivo sai com a mesma cara dos demais relatórios do SGC.

Estrutura = a estrutura dos MENUS:
    Excel → uma aba por menu (Resumo, Quebras, Processos, Desligados)
    PDF   → o Resumo executivo (é o formato que a diretoria lê); o detalhamento linha a linha
            fica no Excel, que é onde ele é utilizável.

Célula vazia num campo de valor significa "omitido por Dados sensíveis" — o serviço já entrega
`None` nesse caso, e nunca 0, para não confundir "não pode ver" com "é zero".
"""

from __future__ import annotations

from typing import Any

from app.services.export.builders import (
    build_executive_pdf_bytes,
    build_multisheet_operational_xlsx_bytes,
    format_brl,
    format_date_br,
)
from app.services.export.report_meta import ReportContext, friendly_filename, header_lines
from app.services.operational_report_export import MIME_PDF, MIME_XLSX, Col

# Uma entrada por ABA: (título, chave no payload, colunas). Espelha as telas do módulo.
_LEGAL_SHEETS: list[tuple[str, str, list[Col]]] = [
    (
        "Resumo",
        "resumo",
        [
            Col("Indicador", "indicador"),
            Col("Quantidade", "quantidade"),
            Col("Valor", "valor", money=True),
        ],
    ),
    (
        "Quebras",
        "quebras",
        [
            Col("Agrupamento", "grupo"),
            Col("Item", "item"),
            Col("Processos", "quantidade"),
            Col("Passivo considerado", "valor", money=True),
        ],
    ),
    (
        "Processos",
        "processos",
        [
            Col("Processo", "processo"),
            Col("Nome", "nome"),
            Col("CPF", "cpf"),
            Col("Empresa", "empresa"),
            Col("Projeto", "projeto"),
            Col("Cliente", "cliente"),
            Col("UF", "uf"),
            Col("Foro", "foro"),
            Col("Comarca", "comarca"),
            Col("Tipo", "tipo"),
            Col("Status", "status"),
            Col("Classe processual", "classe"),
            Col("Reclamante", "reclamante"),
            Col("Reclamado", "reclamado"),
            Col("Valor da causa", "valor_causa", money=True),
            Col("Valor considerado", "valor_considerado", money=True),
            Col("Valor acordado", "valor_acordado", money=True),
            Col("Valor pago", "valor_pago", money=True),
            Col("Valor pendente", "valor_pendente", money=True),
            Col("Condições do acordo", "condicoes_acordo"),
            Col("Última movimentação", "ultima_movimentacao"),
            Col("Data da movimentação", "data_movimentacao", is_date=True),
            Col("Audiência", "audiencia", is_date=True),
            Col("Distribuição", "distribuicao", is_date=True),
            Col("Link JusBrasil", "jusbrasil"),
            Col("Situação do cadastro", "situacao_cadastro"),
            Col("Observações", "observacoes"),
        ],
    ),
    (
        "Desligados",
        "desligados",
        [
            Col("Nome", "nome"),
            Col("CPF", "cpf"),
            Col("Empresa", "empresa"),
            Col("Projeto", "projeto"),
            Col("Cliente", "cliente"),
            Col("Cargo", "cargo"),
            Col("Admissão", "admissao", is_date=True),
            Col("Desligamento", "desligamento", is_date=True),
            Col("Qtd. processos", "qtd_processos"),
            Col("Valor da causa (total)", "valor_causa_total", money=True),
            Col("Valor considerado (total)", "valor_considerado_total", money=True),
            Col("Valor acordado (total)", "valor_acordado_total", money=True),
            Col("Valor pago (total)", "valor_pago_total", money=True),
            Col("Valor pendente (total)", "valor_pendente_total", money=True),
            Col("Rescisão", "rescisao", money=True),
            Col("Saldo FGTS", "fgts", money=True),
            Col("Situação do cadastro", "situacao_cadastro"),
            Col("Observações", "observacoes"),
        ],
    ),
]


def _xlsx_cell(row: dict[str, Any], col: Col) -> Any:
    val = row.get(col.key)
    if col.money:
        # None = redigido por Dados sensíveis → célula vazia (nunca 0).
        return float(val) if isinstance(val, (int, float)) else ""
    if col.is_date and val:
        return format_date_br(str(val)[:10])
    return "" if val is None else val


def _pdf_cell(row: dict[str, Any], col: Col) -> str:
    val = row.get(col.key)
    if col.money:
        return format_brl(val) if isinstance(val, (int, float)) else "—"
    if col.is_date and val:
        return format_date_br(str(val)[:10])
    return "" if val is None else str(val)


def render_legal_report_bytes(
    report_type: str,
    payload: dict[str, Any],
    fmt: str,
    ctx: ReportContext | None = None,
) -> tuple[bytes, str, str]:
    periodo_token = ctx.periodo_token if ctx else None

    if fmt == "xlsx":
        sheets: list[dict[str, Any]] = []
        for title, key, cols in _LEGAL_SHEETS:
            rows = payload.get(key) or []
            sheets.append(
                {
                    "title": title,
                    "headers": [c.header for c in cols],
                    "rows": [[_xlsx_cell(r, c) for c in cols] for r in rows],
                    "money_columns": frozenset(i for i, c in enumerate(cols, start=1) if c.money),
                }
            )
        raw = build_multisheet_operational_xlsx_bytes(sheets)
        return raw, friendly_filename(report_type, "xlsx", periodo_token=periodo_token), MIME_XLSX

    if fmt == "pdf":
        # PDF = leitura executiva: indicadores + quebras. O detalhamento vai no Excel.
        _, _, resumo_cols = _LEGAL_SHEETS[0]
        _, _, quebra_cols = _LEGAL_SHEETS[1]
        rows: list[list[str]] = [
            [r["indicador"], "" if r.get("quantidade") is None else str(r["quantidade"]),
             _pdf_cell(r, resumo_cols[2])]
            for r in (payload.get("resumo") or [])
        ]
        rows.append(["", "", ""])
        for r in payload.get("quebras") or []:
            rows.append([f"{r['grupo']} · {r['item']}", str(r.get("quantidade") or 0),
                         _pdf_cell(r, quebra_cols[3])])

        counts = [
            f"Processos no relatório: {len(payload.get('processos') or [])}",
            f"Desligados no relatório: {len(payload.get('desligados') or [])}",
        ]
        meta = list(header_lines(ctx, include_title=False, include_gen=False)) + counts
        raw = build_executive_pdf_bytes(
            title=(ctx.title if ctx else "Jurídico"),
            headers=["Indicador", "Qtd.", "Valor"],
            rows=rows,
            meta_lines=meta,
        )
        return raw, friendly_filename(report_type, "pdf", periodo_token=periodo_token), MIME_PDF

    raise ValueError("formato inválido")
