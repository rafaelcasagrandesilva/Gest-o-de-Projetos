"""Extração de dados da NFS-e (Nota Fiscal Eletrônica de Serviços) do município de São Paulo.

Lê a camada de texto do PDF e devolve os campos que alimentam o cadastro de NF.
NÃO grava nada: o resultado é uma sugestão que o usuário confere e confirma na tela.

Escopo: layout da NFS-e da Prefeitura de São Paulo (nfe.prefeitura.sp.gov.br).
PDFs que são apenas imagem (impressão/screenshot da nota, sem camada de texto) não
são suportados — exigiriam OCR. O parser detecta esse caso e devolve erro explícito.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO

# Retenções aplicadas sobre o valor bruto para chegar ao líquido a receber.
# Fórmula validada com o contador e conferida contra o "Valor líquido a receber"
# declarado nas próprias notas (NFs 3383, 3397, 3408, 3417 e 3424 — bate ao centavo).
RETENTION_IRRF = Decimal("0.015")  # IRRF 1,5%
RETENTION_PIS = Decimal("0.0065")  # PIS 0,65%
RETENTION_COFINS = Decimal("0.03")  # COFINS 3%
RETENTION_CSLL = Decimal("0.01")  # CSLL 1%
RETENTION_TOTAL = RETENTION_IRRF + RETENTION_PIS + RETENTION_COFINS + RETENTION_CSLL  # 6,15%
NET_FACTOR = Decimal("1") - RETENTION_TOTAL  # 0,9385

# Texto mínimo para considerar que o PDF tem camada de texto aproveitável.
# Uma NFS-e completa rende ~4.000 caracteres; um PDF só-imagem rende ~0.
_MIN_TEXT_LENGTH = 500

_MONTHS = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "março": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}

# Traços usados entre mês e ano na discriminação: hífen, en-dash e em-dash.
_DASHES = r"[-–—]"


class NfseParseError(Exception):
    """PDF não pôde ser interpretado como NFS-e de São Paulo."""


@dataclass
class ParsedNfse:
    """Campos extraídos de uma NFS-e. Todos opcionais menos os que a nota sempre traz."""

    nf_number: str | None = None
    issue_date: date | None = None
    competence_month: date | None = None
    gross_amount: Decimal | None = None
    net_amount: Decimal | None = None
    declared_net_amount: Decimal | None = None
    client_name: str | None = None
    client_document: str | None = None
    contract_number: str | None = None
    description: str | None = None
    warnings: list[str] = field(default_factory=list)


def _parse_money(raw: str) -> Decimal:
    """Converte "80.196,85" em Decimal("80196.85")."""
    return Decimal(raw.replace(".", "").replace(",", "."))


def _round2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compute_net_amount(gross: Decimal) -> Decimal:
    """Líquido a receber = bruto menos as retenções (IRRF + PIS + COFINS + CSLL)."""
    return _round2(gross * NET_FACTOR)


def extract_pdf_text(content: bytes) -> str:
    """Texto da primeira página preservando o layout em colunas da nota."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependência declarada em requirements
        raise NfseParseError("Leitor de PDF indisponível no servidor.") from exc

    try:
        reader = PdfReader(BytesIO(content))
    except Exception as exc:
        raise NfseParseError("Não foi possível abrir o PDF.") from exc

    if not reader.pages:
        raise NfseParseError("PDF sem páginas.")

    try:
        return reader.pages[0].extract_text(extraction_mode="layout") or ""
    except Exception:
        # Alguns PDFs falham no modo layout; o modo simples ainda permite os regexes
        # que não dependem de alinhamento em colunas.
        try:
            return reader.pages[0].extract_text() or ""
        except Exception as exc:
            raise NfseParseError("Não foi possível ler o texto do PDF.") from exc


def parse_nfse_text(text: str) -> ParsedNfse:
    """Aplica os padrões da NFS-e paulistana sobre o texto já extraído."""
    out = ParsedNfse()

    # Número da nota: rótulo e valor ficam em colunas distintas, o valor vem
    # nas linhas seguintes com zeros à esquerda (ex.: "00003424").
    m = re.search(r"Número da Nota\s*\n.*?(\d{6,})", text, re.S)
    if m:
        out.nf_number = str(int(m.group(1)))

    # Data e hora de emissão: "04/08/2026 17:56:47".
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})\s+\d{2}:\d{2}:\d{2}", text)
    if m:
        day, month, year = (int(g) for g in m.groups())
        try:
            out.issue_date = date(year, month, day)
        except ValueError:
            out.warnings.append("Data de emissão inválida no PDF.")

    # Tomador = cliente. O bloco do prestador (M&E) vem antes e não interessa.
    m = re.search(r"TOMADOR DE SERVIÇOS\s*\n\s*Nome/Razão Social:\s*(.+)", text)
    if m:
        out.client_name = m.group(1).strip() or None
    m = re.search(r"TOMADOR DE SERVIÇOS\s*\n.*?CPF/CNPJ:\s*([\d./-]{11,})", text, re.S)
    if m:
        out.client_document = m.group(1).strip()

    # Valor bruto.
    m = re.search(r"VALOR TOTAL DO SERVIÇO\s*=\s*R\$\s*([\d.,]+)", text)
    if m:
        out.gross_amount = _parse_money(m.group(1))

    # Líquido declarado na discriminação — opcional e digitado à mão pelo emissor
    # (nem toda nota traz, e os dois pontos após "receber" variam). Serve só
    # para conferência contra a fórmula.
    m = re.search(r"[Vv]alor l[íi]quido a receber:?\s*R\$\s*([\d.,]+)", text)
    if m:
        out.declared_net_amount = _parse_money(m.group(1))

    # Contrato: usado para casar a NF com o projeto (projects.contract_number).
    m = re.search(r"Contrato\s*n[ºo°]?\.?\s*([\w./-]+)", text)
    if m:
        out.contract_number = m.group(1).strip().rstrip(".")

    # Competência: linha isolada "Julho – 2026" dentro da discriminação.
    m = re.search(
        rf"(?im)^\s*({'|'.join(_MONTHS)})\s*{_DASHES}\s*(\d{{4}})\s*$",
        text,
    )
    if m:
        out.competence_month = date(int(m.group(2)), _MONTHS[m.group(1).lower()], 1)

    # Descrição: primeira linha da discriminação, sem o rótulo opcional.
    m = re.search(r"DISCRIMINAÇÃO DE SERVIÇOS\s*\n\s*(.+)", text)
    if m:
        desc = m.group(1).strip()
        desc = re.sub(r"^Descrição do Serviço:\s*", "", desc)
        out.description = desc or None

    if out.gross_amount is not None:
        out.net_amount = compute_net_amount(out.gross_amount)
        if (
            out.declared_net_amount is not None
            and out.declared_net_amount != out.net_amount
        ):
            out.warnings.append(
                f"O líquido calculado (R$ {out.net_amount}) difere do valor escrito na "
                f"nota (R$ {out.declared_net_amount}). Confira antes de confirmar."
            )

    return out


def parse_nfse_pdf(content: bytes) -> ParsedNfse:
    """Ponto de entrada: bytes do PDF → campos da NF."""
    text = extract_pdf_text(content)
    if len(text.strip()) < _MIN_TEXT_LENGTH:
        raise NfseParseError(
            "Este PDF é uma imagem digitalizada da nota — o texto não pode ser extraído. "
            "Cadastre a NF manualmente e anexe o arquivo."
        )

    parsed = parse_nfse_text(text)

    # Sem número e sem valor não há o que aproveitar: provavelmente não é uma NFS-e de SP.
    if parsed.nf_number is None and parsed.gross_amount is None:
        raise NfseParseError(
            "Não reconheci este PDF como uma NFS-e de São Paulo. Cadastre a NF manualmente."
        )

    if parsed.nf_number is None:
        parsed.warnings.append("Não encontrei o número da nota.")
    if parsed.gross_amount is None:
        parsed.warnings.append("Não encontrei o valor bruto.")
    if parsed.issue_date is None:
        parsed.warnings.append("Não encontrei a data de emissão.")
    if parsed.competence_month is None:
        parsed.warnings.append("Não encontrei a competência na discriminação da nota.")

    return parsed
