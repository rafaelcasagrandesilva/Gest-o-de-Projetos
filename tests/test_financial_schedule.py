"""Núcleo genérico do Cronograma Financeiro (domain-agnostic). Testes puros, sem banco."""

from datetime import date
from decimal import Decimal

import pytest

from app.services.financial_schedule import (
    RangeSpec,
    build_schedule,
    compute_indicators,
    expand_range,
    schedule_total,
    validate_closure,
)


def test_expand_range_rolls_months_and_keeps_day():
    lines = expand_range(
        RangeSpec(seq_start=1, seq_end=6, amount=Decimal("15000"), day=20, first_due_month=date(2026, 8, 1))
    )
    assert [ln.due_date for ln in lines] == [
        date(2026, 8, 20),
        date(2026, 9, 20),
        date(2026, 10, 20),
        date(2026, 11, 20),
        date(2026, 12, 20),
        date(2027, 1, 20),
    ]
    assert [ln.seq for ln in lines] == [1, 2, 3, 4, 5, 6]
    assert all(ln.amount == Decimal("15000.00") for ln in lines)
    assert lines[0].description == "Parcela 1"


def test_expand_range_clamps_day_to_month_end():
    lines = expand_range(
        RangeSpec(seq_start=1, seq_end=2, amount=Decimal("100"), day=31, first_due_month=date(2027, 1, 1))
    )
    assert lines[0].due_date == date(2027, 1, 31)
    assert lines[1].due_date == date(2027, 2, 28)  # fevereiro


def test_build_schedule_from_three_ranges():
    schedule = build_schedule(
        [
            RangeSpec(1, 6, Decimal("15000"), 20, date(2026, 8, 1)),
            RangeSpec(7, 12, Decimal("20000"), 20, date(2027, 2, 1)),
            RangeSpec(13, 30, Decimal("110000"), 20, date(2027, 8, 1)),
        ]
    )
    assert len(schedule) == 30
    assert schedule[0].seq == 1 and schedule[-1].seq == 30
    assert schedule[-1].due_date == date(2029, 1, 20)  # encerra jan/2029
    expected_total = Decimal("15000") * 6 + Decimal("20000") * 6 + Decimal("110000") * 18
    assert schedule_total(schedule) == expected_total.quantize(Decimal("0.01"))


def test_build_schedule_rejects_gap():
    with pytest.raises(ValueError):
        build_schedule(
            [
                RangeSpec(1, 6, Decimal("15000"), 20, date(2026, 8, 1)),
                RangeSpec(8, 12, Decimal("20000"), 20, date(2027, 2, 1)),  # lacuna: falta 7
            ]
        )


def test_build_schedule_requires_start_at_one():
    with pytest.raises(ValueError):
        build_schedule([RangeSpec(2, 6, Decimal("15000"), 20, date(2026, 8, 1))])


def test_validate_closure_valid_and_invalid():
    schedule = build_schedule([RangeSpec(1, 3, Decimal("1000"), 10, date(2026, 8, 1))])
    ok = validate_closure(Decimal("3000"), schedule)
    assert ok.is_valid and ok.diferenca == Decimal("0.00")

    bad = validate_closure(Decimal("3300"), schedule)
    assert not bad.is_valid
    assert bad.diferenca == Decimal("300.00")  # negociado - cronograma
    assert bad.total_cronograma == Decimal("3000.00")


def test_compute_indicators_uses_real_payments_not_planned():
    """Parcelas planejadas NÃO contam como pagas: só os pagamentos reais por parcela contam."""
    schedule = build_schedule([RangeSpec(1, 4, Decimal("1000"), 10, date(2026, 8, 1))])

    # Nenhum pagamento real ainda → 0% pago, apesar do cronograma somar 4.000.
    zero = compute_indicators(total_negociado=Decimal("4000"), lines=schedule, paid_by_seq={})
    assert zero.total_cronograma == Decimal("4000.00")
    assert zero.total_pago == Decimal("0.00")
    assert zero.saldo_restante == Decimal("4000.00")
    assert zero.progresso == 0.0
    assert zero.parcelas_pagas == 0
    assert zero.parcelas_restantes == 4
    assert zero.proxima_parcela.seq == 1
    assert zero.ultima_parcela.seq == 4
    assert zero.data_encerramento == date(2026, 11, 10)

    # Parcelas 1 e 2 pagas de fato (CAP) → 50% pago, próxima é a 3.
    half = compute_indicators(
        total_negociado=Decimal("4000"),
        lines=schedule,
        paid_by_seq={1: Decimal("1000"), 2: Decimal("1000")},
    )
    assert half.total_pago == Decimal("2000.00")
    assert half.saldo_restante == Decimal("2000.00")
    assert half.progresso == 0.5
    assert half.parcelas_pagas == 2
    assert half.parcelas_restantes == 2
    assert half.proxima_parcela.seq == 3


def test_compute_indicators_partial_payment_line_not_counted_paid():
    schedule = build_schedule([RangeSpec(1, 2, Decimal("1000"), 10, date(2026, 8, 1))])
    ind = compute_indicators(
        total_negociado=Decimal("2000"),
        lines=schedule,
        paid_by_seq={1: Decimal("400")},  # pagamento parcial: parcela 1 ainda aberta
    )
    assert ind.total_pago == Decimal("400.00")
    assert ind.parcelas_pagas == 0
    assert ind.proxima_parcela.seq == 1
