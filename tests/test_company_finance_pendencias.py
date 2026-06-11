"""Testes das regras puras de pendências de lançamento (custos fixos obrigatórios).

Cobrem o critério de validação obrigatório:
- item obrigatório sem valor na competência => pendência;
- item obrigatório com valor na competência => sem pendência;
- item não obrigatório => nunca gera pendência;
- "último valor conhecido" = competência anterior mais recente com valor > 0.

São regras de monitoramento: não criam lançamento, conta a pagar ou título zerado.
"""

from __future__ import annotations

import unittest
from datetime import date

from app.services.company_finance_service import is_lancamento_pendente, last_known_payment


class TestIsLancamentoPendente(unittest.TestCase):
    def test_obrigatorio_sem_valor_gera_pendencia(self) -> None:
        self.assertTrue(
            is_lancamento_pendente(is_monthly_required=True, has_value_in_competencia=False)
        )

    def test_obrigatorio_com_valor_nao_gera_pendencia(self) -> None:
        self.assertFalse(
            is_lancamento_pendente(is_monthly_required=True, has_value_in_competencia=True)
        )

    def test_nao_obrigatorio_sem_valor_nao_gera_pendencia(self) -> None:
        self.assertFalse(
            is_lancamento_pendente(is_monthly_required=False, has_value_in_competencia=False)
        )

    def test_nao_obrigatorio_com_valor_nao_gera_pendencia(self) -> None:
        self.assertFalse(
            is_lancamento_pendente(is_monthly_required=False, has_value_in_competencia=True)
        )


class TestLastKnownPayment(unittest.TestCase):
    def test_competencia_anterior_mais_recente_com_valor(self) -> None:
        payments = [
            (date(2026, 4, 1), 1100.0),
            (date(2026, 5, 1), 0.0),
            (date(2026, 6, 1), 1205.94),
        ]
        result = last_known_payment(payments, date(2026, 7, 1))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result[0], date(2026, 6, 1))
        self.assertAlmostEqual(result[1], 1205.94)

    def test_ignora_competencias_futuras(self) -> None:
        payments = [
            (date(2026, 6, 1), 1205.94),
            (date(2026, 8, 1), 1300.0),  # futura — não conta
        ]
        result = last_known_payment(payments, date(2026, 7, 1))
        assert result is not None
        self.assertEqual(result[0], date(2026, 6, 1))

    def test_ignora_valores_zero(self) -> None:
        payments = [
            (date(2026, 5, 1), 0.0),
            (date(2026, 6, 1), 0.0),
        ]
        self.assertIsNone(last_known_payment(payments, date(2026, 7, 1)))

    def test_sem_historico_retorna_none(self) -> None:
        self.assertIsNone(last_known_payment([], date(2026, 7, 1)))

    def test_competencia_atual_nao_e_historico(self) -> None:
        # valor na própria competência não conta como "último valor conhecido" anterior
        payments = [(date(2026, 7, 1), 999.0)]
        self.assertIsNone(last_known_payment(payments, date(2026, 7, 1)))


if __name__ == "__main__":
    unittest.main()
