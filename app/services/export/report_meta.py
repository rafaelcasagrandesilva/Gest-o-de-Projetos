"""Metadados de relatórios: nomes amigáveis, nome de arquivo e cabeçalho de identificação.

Centraliza a nomenclatura (item 6/7) e o bloco de identificação (item 8) usados
por TODOS os exportadores. Nada aqui altera cálculo, filtro ou regra de negócio —
é exclusivamente apresentação/rotulagem da exportação.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

# report_type (do router) -> nome amigável em português (usado no arquivo e no título).
REPORT_TITLES: dict[str, str] = {
    "project_summary": "Projeto - Resumo Financeiro e Custos",
    "company_summary": "Empresa - Resumo Financeiro por Projeto",
    "employees": "Colaboradores",
    "payroll": "Folha de Pagamento",
    "vehicles": "Frota",
    "invoices": "Notas Fiscais - Resumo",
    "invoices_detailed": "Notas Fiscais - Detalhado",
    "debt": "Endividamento - Matriz Mensal",
    "fixed_costs": "Custos Fixos - Matriz Mensal",
    "users": "Usuários do Sistema",
    "revenues": "Receitas Lançadas",
    "dashboard": "Dashboard - Série Mensal Receita, Custos e Margem",
    "payables_detailed": "Contas a Pagar - Detalhado",
    "receivables_detailed": "Contas a Receber - Detalhado",
    "assets_inventory": "Inventário Patrimonial",
    "assets_in_use": "Ativos em Uso",
    "assets_inspections": "Inspeções e Vencimentos",
    "assets_movements": "Movimentações Patrimoniais",
}

_MONTHS_PT = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


def report_title(report_type: str) -> str:
    """Nome amigável do relatório (fallback: o próprio tipo)."""
    return REPORT_TITLES.get(report_type, report_type)


@dataclass
class ReportContext:
    """Contexto de auditoria da exportação, montado no router e propagado aos renderers.

    Apenas identificação/rotulagem — não influencia dados. `periodo_token` (quando
    informado) vira o sufixo do nome do arquivo no lugar da data de geração.
    """

    report_type: str
    generated_by: str | None = None
    filters: dict[str, Any] = field(default_factory=dict)
    empresa: str | None = None
    projeto: str | None = None
    periodo: str | None = None
    cenario: str | None = None
    periodo_token: str | None = None

    @property
    def title(self) -> str:
        return report_title(self.report_type)


def _sanitize_filename(name: str) -> str:
    """Mantém letras/números/espaços/acentos e alguns separadores; remove o resto."""
    out = []
    for ch in name:
        if ch.isalnum() or ch in " -_.()":
            out.append(ch)
    cleaned = "".join(out).strip()
    # Colapsa espaços múltiplos.
    return " ".join(cleaned.split())


def friendly_filename(
    report_type: str,
    ext: str,
    *,
    periodo_token: str | None = None,
    gen_date: date | None = None,
) -> str:
    """Nome de arquivo amigável: "Contas a Pagar - Detalhado - 2026-07-04.xlsx".

    Com filtro de período (`periodo_token`), usa o período no lugar da data:
    "Notas Fiscais - Janeiro_2026_a_Junho_2026.xlsx".
    """
    base = report_title(report_type)
    suffix = periodo_token or (gen_date or date.today()).isoformat()
    return f"{_sanitize_filename(base)} - {suffix}.{ext}"


def month_year_token(d: date) -> str:
    """"Janeiro 2026" para uso no nome de arquivo (com espaço, conforme padrão)."""
    return f"{_MONTHS_PT[d.month - 1]} {d.year}"


def month_year_label(d: date) -> str:
    """"Janeiro/2026" para uso no cabeçalho de identificação."""
    return f"{_MONTHS_PT[d.month - 1]}/{d.year}"


def _format_filters(filters: dict[str, Any] | None) -> str:
    if not filters:
        return "nenhum"
    parts: list[str] = []
    for k, v in filters.items():
        if v is None or v == "":
            continue
        parts.append(f"{k}={v}")
    return "; ".join(parts) if parts else "nenhum"


def header_lines(
    ctx: ReportContext | None,
    *,
    record_count: int | None = None,
    include_title: bool = True,
    include_gen: bool = True,
) -> list[str]:
    """Bloco de identificação (item 8) para Excel (aba) e PDF (cabeçalho).

    `include_title`/`include_gen` permitem omitir as linhas que o PDF já imprime
    (título e "Gerado em"), evitando duplicação.
    """
    if ctx is None:
        return []
    lines: list[str] = []
    if include_title:
        lines.append(f"Relatório: {ctx.title}")
    if include_gen:
        gen = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
        lines.append(f"Gerado em: {gen}")
    lines.append(f"Usuário responsável: {ctx.generated_by or '—'}")
    if ctx.empresa:
        lines.append(f"Empresa: {ctx.empresa}")
    if ctx.projeto:
        lines.append(f"Projeto: {ctx.projeto}")
    if ctx.periodo:
        lines.append(f"Período: {ctx.periodo}")
    if ctx.cenario:
        lines.append(f"Cenário: {ctx.cenario}")
    if record_count is not None:
        lines.append(f"Registros: {record_count}")
    lines.append(f"Filtros utilizados: {_format_filters(ctx.filters)}")
    return lines
