from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.export.builders import (
    build_executive_pdf_bytes,
    build_operational_xlsx_bytes,
    format_brl,
    format_date_br,
)
from app.services.export.report_meta import ReportContext, friendly_filename, header_lines

MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MIME_PDF = "application/pdf"


@dataclass(frozen=True)
class Col:
    """Definição de uma coluna do relatório operacional (cabeçalho + chave + tipo)."""

    header: str
    key: str
    money: bool = False
    is_date: bool = False


# Colunas por relatório, na ordem lógica das telas:
# Identificação → Relacionamentos → Valores → Status → Datas → Administrativo.
_OPERATIONAL_COLUMNS: dict[str, list[Col]] = {
    "payables_detailed": [
        Col("Nome", "nome"),
        Col("Categoria", "categoria"),
        Col("Tipo", "tipo"),
        Col("Projeto", "projeto"),
        Col("Centro de custo", "centro_custo"),
        Col("Competência", "competencia"),
        Col("Vencimento", "vencimento", is_date=True),
        Col("Mês pagamento", "mes_pagamento"),
        Col("Data pagamento", "data_pagamento", is_date=True),
        Col("Valor previsto", "valor_original", money=True),
        Col("Valor final", "valor_final", money=True),
        Col("Valor pago", "valor_pago", money=True),
        Col("Saldo", "saldo", money=True),
        Col("Status", "status"),
        Col("Pago", "pago"),
        Col("No dashboard", "no_dashboard"),
        Col("Obsoleto", "obsoleto"),
        Col("Motivo obsolescência", "motivo_obsolescencia"),
        Col("Observações", "observacoes"),
    ],
    "receivables_detailed": [
        Col("Nº NF", "nf"),
        Col("Cliente", "cliente"),
        Col("Projeto", "projeto"),
        Col("Contrato", "contrato"),
        Col("Centro de custo", "centro_custo"),
        Col("Competência", "competencia"),
        Col("Emissão", "emissao", is_date=True),
        Col("Vencimento", "vencimento", is_date=True),
        Col("Recebimento", "recebimento", is_date=True),
        Col("Valor bruto", "valor_bruto", money=True),
        Col("Valor líquido", "valor", money=True),
        Col("Valor antecipado", "valor_antecipado", money=True),
        Col("Recebido", "recebido", money=True),
        Col("Saldo", "saldo", money=True),
        Col("Status", "status"),
        Col("Oficial", "oficial"),
        Col("Antecipada", "antecipada"),
        Col("Instituição", "instituicao"),
        Col("Observações", "observacoes"),
        Col("Origem", "origem"),
    ],
    "invoices_detailed": [
        Col("Nº NF", "numero_nf"),
        Col("Cliente", "cliente"),
        Col("Projeto", "projeto"),
        Col("Contrato", "contrato"),
        Col("Centro de custo", "centro_custo"),
        Col("Competência", "competencia"),
        Col("Emissão", "emissao", is_date=True),
        Col("Vencimento", "vencimento", is_date=True),
        Col("Recebimento", "recebimento", is_date=True),
        Col("Valor bruto", "valor_bruto", money=True),
        Col("Valor líquido", "valor", money=True),
        Col("Valor antecipado", "valor_antecipado", money=True),
        Col("Custo antecipação", "custo_antecipacao", money=True),
        Col("Recebido", "recebido", money=True),
        Col("Saldo", "saldo", money=True),
        Col("Prazo (dias)", "prazo_dias"),
        Col("Status", "status"),
        Col("Oficial", "oficial"),
        Col("Antecipada", "antecipada"),
        Col("Instituição", "instituicao"),
        Col("Vencimento antecipação", "venc_antecipacao", is_date=True),
        Col("No dashboard", "no_dashboard"),
        Col("Observações", "observacoes"),
        Col("Criado em", "criado_em", is_date=True),
        Col("Atualizado em", "atualizado_em", is_date=True),
    ],
    "assets_inventory": [
        Col("Código", "codigo"),
        Col("Item", "item"),
        Col("Categoria", "categoria"),
        Col("Subcategoria", "subcategoria"),
        Col("Tamanho", "tamanho"),
        Col("Marca", "marca"),
        Col("Modelo", "modelo"),
        Col("Nº série", "numero_serie"),
        Col("Patrimônio", "patrimonio"),
        Col("IMEI", "imei"),
        Col("CA", "ca"),
        Col("Tags", "tags"),
        Col("Descrição", "descricao"),
        Col("Responsável", "responsavel"),
        Col("Centro de custo", "centro_custo"),
        Col("Projeto", "projeto"),
        Col("Valor", "valor", money=True),
        Col("Status", "status"),
        Col("Estado físico", "estado_fisico"),
        Col("Data aquisição", "data_aquisicao", is_date=True),
        Col("Observações", "observacoes"),
        Col("Criado em", "criado_em", is_date=True),
        Col("Atualizado em", "atualizado_em", is_date=True),
    ],
    "assets_in_use": [
        Col("Código", "codigo"),
        Col("Item", "item"),
        Col("Marca", "marca"),
        Col("Modelo", "modelo"),
        Col("Nº série", "numero_serie"),
        Col("Patrimônio", "patrimonio"),
        Col("Responsável", "responsavel"),
        Col("Centro de custo", "centro_custo"),
        Col("Projeto", "projeto"),
        Col("Data entrega", "data_entrega", is_date=True),
        Col("Status", "status"),
        Col("Estado físico", "estado_fisico"),
        Col("Valor", "valor", money=True),
    ],
    "assets_inspections": [
        Col("Ativo", "ativo"),
        Col("Tipo inspeção", "tipo_inspecao"),
        Col("Data inspeção", "data_inspecao", is_date=True),
        Col("Validade", "validade", is_date=True),
        Col("Meses validade", "meses_validade"),
        Col("Status validade", "status_validade"),
        Col("Dias restantes", "dias_restantes"),
        Col("Responsável", "responsavel"),
        Col("Alerta", "alerta"),
        Col("Observações", "observacoes"),
    ],
    "assets_movements": [
        Col("Ativo", "ativo"),
        Col("Entregador", "entregador"),
        Col("Recebedor", "recebedor"),
        Col("Data entrega", "data_entrega", is_date=True),
        Col("Data devolução", "data_devolucao", is_date=True),
        Col("Resp. devolução", "responsavel_devolucao"),
        Col("Estado devolução", "estado_devolucao"),
        Col("Observações", "observacoes"),
        Col("Registrado em", "registrado_em", is_date=True),
    ],
}


def _cell_xlsx(row: dict[str, Any], col: Col) -> Any:
    val = row.get(col.key)
    if col.money and isinstance(val, (int, float)):
        return float(val)
    if col.is_date and val:
        return format_date_br(str(val)[:10])
    return "" if val is None else val


def _cell_pdf(row: dict[str, Any], col: Col) -> str:
    val = row.get(col.key)
    if col.money and isinstance(val, (int, float)):
        return format_brl(val)
    if col.is_date and val:
        return format_date_br(str(val)[:10])
    return "" if val is None else str(val)


def render_operational_report_bytes(
    report_type: str,
    payload: dict[str, Any],
    fmt: str,
    ctx: ReportContext | None = None,
) -> tuple[bytes, str, str]:
    if fmt not in ("xlsx", "pdf"):
        raise ValueError("formato inválido")
    cols = _OPERATIONAL_COLUMNS.get(report_type)
    if not cols:
        raise ValueError(f"tipo operacional desconhecido: {report_type}")
    headers = [c.header for c in cols]
    money_cols = frozenset(i for i, c in enumerate(cols, start=1) if c.money)
    raw_rows = payload.get("rows") or []

    from app.services.export.report_meta import report_title

    title = report_title(report_type)
    periodo_token = ctx.periodo_token if ctx else None

    if fmt == "xlsx":
        # Excel abre direto nos dados (sem aba de identificação); o nome amigável
        # do relatório fica no NOME DO ARQUIVO.
        xlsx_rows = [[_cell_xlsx(r, c) for c in cols] for r in raw_rows]
        raw = build_operational_xlsx_bytes(
            headers=headers,
            rows=xlsx_rows,
            sheet_title=title[:31],
            money_columns=money_cols,
        )
        return raw, friendly_filename(report_type, "xlsx", periodo_token=periodo_token), MIME_XLSX

    pdf_rows = [[_cell_pdf(r, c) for c in cols] for r in raw_rows]
    # No PDF o título e o "Gerado em" já são impressos pelo builder → não duplicar.
    meta = header_lines(ctx, record_count=len(raw_rows), include_title=False, include_gen=False)
    raw = build_executive_pdf_bytes(title=title, headers=headers, rows=pdf_rows, meta_lines=meta)
    return raw, friendly_filename(report_type, "pdf", periodo_token=periodo_token), MIME_PDF
