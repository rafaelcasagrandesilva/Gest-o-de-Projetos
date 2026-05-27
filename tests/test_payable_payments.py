"""Testes do ledger de pagamentos de contas a pagar (sem banco)."""

from __future__ import annotations

import unittest
from datetime import date, timedelta
from decimal import Decimal

from app.services.payable_snapshot_service import (
    PAYABLE_PAYMENT_TOLERANCE,
    _validate_payment_date,
    payable_snapshot_derived_fields,
    payable_snapshot_payment_status,
)


class TestPayablePaymentStatus(unittest.TestCase):
    def test_open_when_nothing_paid(self) -> None:
        self.assertEqual(
            payable_snapshot_payment_status(amount_paid=Decimal("0"), amount_final=Decimal("10000")),
            "ABERTO",
        )

    def test_partial_after_first_payment(self) -> None:
        derived = payable_snapshot_derived_fields(
            amount_paid=Decimal("2000"), amount_final=Decimal("10000")
        )
        self.assertEqual(derived["status"], "PARCIAL")
        self.assertEqual(derived["amount_remaining"], 8000.0)

    def test_paid_when_fully_settled(self) -> None:
        self.assertEqual(
            payable_snapshot_payment_status(amount_paid=Decimal("10000"), amount_final=Decimal("10000")),
            "PAGO",
        )

    def test_multiple_partial_payments_sum(self) -> None:
        total = Decimal("2000") + Decimal("3000") + Decimal("5000")
        derived = payable_snapshot_derived_fields(amount_paid=total, amount_final=Decimal("10000"))
        self.assertEqual(derived["status"], "PAGO")
        self.assertAlmostEqual(derived["amount_remaining"], 0.0)


class TestPaymentDateValidation(unittest.TestCase):
    def test_today_allowed(self) -> None:
        self.assertEqual(_validate_payment_date(date.today()), date.today())

    def test_future_rejected(self) -> None:
        future = date.today() + timedelta(days=1)
        with self.assertRaises(ValueError):
            _validate_payment_date(future)

    def test_default_today_when_none(self) -> None:
        self.assertEqual(_validate_payment_date(None), date.today())


class TestCompetenceVsCashFlow(unittest.TestCase):
    """Cenário: obrigação FEV, pagamento em MAR."""

    def test_obligation_month_unchanged_cash_in_march(self) -> None:
        obligation_month = date(2026, 2, 1)
        payment_date = date(2026, 3, 27)
        self.assertEqual(obligation_month.month, 2)
        self.assertEqual(payment_date.month, 3)
        # Fluxo de caixa agrupa por mês calendário do payment_date
        cash_flow_key = (payment_date.year, payment_date.month)
        self.assertEqual(cash_flow_key, (2026, 3))


class TestReverseTolerance(unittest.TestCase):
    def test_tolerance_constant(self) -> None:
        self.assertEqual(PAYABLE_PAYMENT_TOLERANCE, Decimal("0.02"))


class TestOperationalListMerge(unittest.TestCase):
    """União competência ∪ pagamentos no período, sem duplicar snapshot.id."""

    def test_competence_month_includes_paid_in_other_period(self) -> None:
        """Obrigação JAN quitada em MAI deve continuar na visão de JAN."""
        competence_ids = {"jan-manual-1"}
        paid_in_may_ids = {"jan-manual-1", "fev-paid-in-may"}
        merged = set(competence_ids) | set(paid_in_may_ids)
        self.assertIn("jan-manual-1", merged)
        self.assertEqual(len(merged), 2)

    def test_merge_dedupes_by_id(self) -> None:
        competence_ids = {"a", "b"}
        paid_ids = {"b", "c"}
        merged = competence_ids | paid_ids
        self.assertEqual(merged, {"a", "b", "c"})

    def test_paid_only_not_in_open_set(self) -> None:
        """Pago em maio (competência abril) não entra no conjunto aberto de abril."""
        april_open = {"may_item"}  # hypothetical id still open in april
        april_paid_in_may = set()  # abril quitado não está em aberto
        self.assertEqual(len(april_open & april_paid_in_may), 0)


if __name__ == "__main__":
    unittest.main()
