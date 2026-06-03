"""Regressão: parsing monetário pt-BR e valores da API (ponto decimal)."""

from decimal import Decimal

import pytest

from app.utils.money import money_to_float, normalize_money, parse_currency_input, round_money


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("365.575,21", Decimal("365575.21")),
        ("10.000,00", Decimal("10000.00")),
        ("1.234,56", Decimal("1234.56")),
        ("0,01", Decimal("0.01")),
        ("0,10", Decimal("0.10")),
        ("100.000.000,99", Decimal("100000000.99")),
        ("R$ 365.575,21", Decimal("365575.21")),
        # Valor como vem de String(number) na UI legada — não pode virar 36557521
        ("365575.21", Decimal("365575.21")),
        ("1250.5", Decimal("1250.50")),
        ("500", Decimal("500.00")),
    ],
)
def test_parse_currency_input_pt_br_and_api_strings(raw: str, expected: Decimal) -> None:
    assert parse_currency_input(raw) == expected


def test_parse_currency_input_rejects_wrong_scale() -> None:
    """Bug reportado: 365575.21 não pode virar 36557521."""
    assert parse_currency_input("365575.21") != Decimal("36557521.00")
    assert money_to_float(parse_currency_input("365575.21")) == 365575.21


@pytest.mark.parametrize(
    "api_value,expected",
    [
        (365575.21, Decimal("365575.21")),
        (10000.0, Decimal("10000.00")),
        (0.01, Decimal("0.01")),
    ],
)
def test_normalize_money_from_api_number(api_value: float, expected: Decimal) -> None:
    assert normalize_money(api_value) == expected


def test_edit_only_description_preserves_amount() -> None:
    """Simula: registro salvo com 365575.21, formulário recarrega e salva sem alterar valor."""
    stored = Decimal("365575.21")
    # Campo formatado como na UI corrigida
    field = "365.575,21"
    reparsed = parse_currency_input(field)
    assert reparsed == stored
    assert money_to_float(reparsed) == money_to_float(stored)


def test_round_money_two_decimals() -> None:
    assert round_money(1.005) == Decimal("1.01") or round_money(1.005) == Decimal("1.00")
