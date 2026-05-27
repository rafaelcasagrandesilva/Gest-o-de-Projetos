from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.services.payable_import.constants import REQUIRED_MAPPING_FIELDS
from app.services.payable_import.normalization import (
    cell_str,
    default_category,
    normalize_text,
    parse_amount,
    parse_date,
)
from app.utils.date_utils import normalize_competencia


@dataclass(frozen=True)
class ColumnMapping:
    name: str | None = None
    cost_center: str | None = None
    due_date: str | None = None
    amount: str | None = None
    category: str | None = None
    observation: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ColumnMapping:
        return cls(
            name=data.get("name") or None,
            cost_center=data.get("cost_center") or None,
            due_date=data.get("due_date") or None,
            amount=data.get("amount") or None,
            category=data.get("category") or None,
            observation=data.get("observation") or None,
        )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "name": self.name,
            "cost_center": self.cost_center,
            "due_date": self.due_date,
            "amount": self.amount,
            "category": self.category,
            "observation": self.observation,
        }

    def validate(self) -> None:
        missing = [f for f in REQUIRED_MAPPING_FIELDS if not getattr(self, f)]
        if missing:
            labels = {
                "name": "Nome / descrição",
                "cost_center": "Centro de custo",
                "due_date": "Vencimento",
                "amount": "Valor",
            }
            raise ValueError(
                "Mapeamento incompleto. Campos obrigatórios: "
                + ", ".join(labels.get(m, m) for m in missing)
            )


@dataclass(frozen=True)
class ParsedImportRow:
    line_number: int
    cost_center: str
    name: str
    due_date: date
    amount: Decimal
    observation: str | None
    category: str
    payment_month: date


def _get_cell(row: dict[str, Any], column: str | None) -> Any:
    if not column:
        return None
    return row.get(column)


def parse_mapped_row(
    *,
    line_number: int,
    row: dict[str, Any],
    mapping: ColumnMapping,
) -> tuple[ParsedImportRow | None, str | None, bool]:
    """Retorna (parsed, erro, is_empty)."""
    if not any(cell_str(v) for v in row.values()):
        return None, None, True

    name = normalize_text(_get_cell(row, mapping.name))
    cost_center = normalize_text(_get_cell(row, mapping.cost_center))
    due = parse_date(_get_cell(row, mapping.due_date))
    amount = parse_amount(_get_cell(row, mapping.amount))
    observation_raw = _get_cell(row, mapping.observation)
    observation = normalize_text(observation_raw) or None
    category = default_category(_get_cell(row, mapping.category) if mapping.category else None)

    if not name:
        return None, "Nome/descrição obrigatório.", False
    if not cost_center:
        return None, "Centro de custo obrigatório.", False
    if due is None:
        return None, "Data de vencimento inválida.", False
    if amount is None:
        return None, "Valor inválido.", False

    return (
        ParsedImportRow(
            line_number=line_number,
            cost_center=cost_center,
            name=name,
            due_date=due,
            amount=amount,
            observation=observation,
            category=category,
            payment_month=normalize_competencia(due),
        ),
        None,
        False,
    )


def suggest_mapping(columns: list[str]) -> dict[str, str | None]:
    """Heurística para pré-preencher mapeamento."""

    def pick(*needles: str) -> str | None:
        for col in columns:
            low = col.casefold()
            if any(n in low for n in needles):
                return col
        return None

    return {
        "name": pick("fornecedor", "nome", "descri", "favorecido", "benefici"),
        "cost_center": pick("empresa", "centro", "custo", "projeto"),
        "due_date": pick("data", "venc", "pagamento"),
        "amount": pick("valor", "pago", "total"),
        "category": pick("categoria", "de para", "de-para", "de_para", "tipo"),
        "observation": pick("observ", "hist", "coment", "nota"),
    }


def _format_original_date(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    raw = cell_str(value)
    return raw or None


def extract_mapped_original(row: dict[str, Any], mapping: ColumnMapping) -> dict[str, str | None]:
    """Extrai os valores originais (texto) das colunas mapeadas, para exibir no preview."""
    return {
        "original_name": cell_str(_get_cell(row, mapping.name)) or None,
        "original_cost_center": cell_str(_get_cell(row, mapping.cost_center)) or None,
        "original_due_date": _format_original_date(_get_cell(row, mapping.due_date)),
        "original_amount": cell_str(_get_cell(row, mapping.amount)) or None,
        "original_category": cell_str(_get_cell(row, mapping.category)) or None if mapping.category else None,
        "original_observation": cell_str(_get_cell(row, mapping.observation)) or None if mapping.observation else None,
    }
