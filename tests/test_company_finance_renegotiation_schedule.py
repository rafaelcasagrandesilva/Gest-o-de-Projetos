"""Testes das regras puras do cronograma de renegociação (obrigatoriedade automática).

Cobrem a derivação da parcela esperada por competência a partir do cronograma
mensal (mês-âncora + quantidade de parcelas). São regras de monitoramento:
não criam lançamento, conta a pagar ou título zerado.
"""

from __future__ import annotations

import unittest
from datetime import date

from app.services.company_finance_service import (
    add_months,
    first_of_month,
    months_between,
    parcela_prevista_na_competencia,
    renegotiation_installment_count,
)


class TestDateHelpers(unittest.TestCase):
    def test_first_of_month(self) -> None:
        self.assertEqual(first_of_month(date(2026, 6, 24)), date(2026, 6, 1))

    def test_add_months_simples(self) -> None:
        self.assertEqual(add_months(date(2026, 1, 1), 3), date(2026, 4, 1))

    def test_add_months_virada_de_ano(self) -> None:
        self.assertEqual(add_months(date(2026, 11, 1), 3), date(2027, 2, 1))

    def test_months_between(self) -> None:
        self.assertEqual(months_between(date(2026, 1, 1), date(2026, 6, 1)), 5)
        self.assertEqual(months_between(date(2026, 6, 1), date(2026, 1, 1)), -5)
        self.assertEqual(months_between(date(2025, 12, 1), date(2026, 2, 1)), 2)


class TestRenegotiationInstallmentCount(unittest.TestCase):
    def test_installments_usa_contagem(self) -> None:
        self.assertEqual(
            renegotiation_installment_count(renegotiation_type="INSTALLMENTS", installment_count=12), 12
        )

    def test_unique_parcela_unica(self) -> None:
        self.assertEqual(
            renegotiation_installment_count(renegotiation_type="UNIQUE", installment_count=None), 1
        )

    def test_installments_sem_contagem_cai_para_um(self) -> None:
        self.assertEqual(
            renegotiation_installment_count(renegotiation_type="INSTALLMENTS", installment_count=None), 1
        )


class TestParcelaPrevistaNaCompetencia(unittest.TestCase):
    def test_primeira_parcela(self) -> None:
        self.assertTrue(
            parcela_prevista_na_competencia(
                anchor_month=date(2026, 1, 1), installment_count=6, competencia=date(2026, 1, 1)
            )
        )

    def test_parcela_no_meio_da_janela(self) -> None:
        self.assertTrue(
            parcela_prevista_na_competencia(
                anchor_month=date(2026, 1, 1), installment_count=6, competencia=date(2026, 4, 1)
            )
        )

    def test_ultima_parcela_inclusa(self) -> None:
        self.assertTrue(
            parcela_prevista_na_competencia(
                anchor_month=date(2026, 1, 1), installment_count=6, competencia=date(2026, 6, 1)
            )
        )

    def test_apos_ultima_parcela_nao_prevista(self) -> None:
        self.assertFalse(
            parcela_prevista_na_competencia(
                anchor_month=date(2026, 1, 1), installment_count=6, competencia=date(2026, 7, 1)
            )
        )

    def test_antes_do_inicio_nao_prevista(self) -> None:
        self.assertFalse(
            parcela_prevista_na_competencia(
                anchor_month=date(2026, 3, 1), installment_count=6, competencia=date(2026, 2, 1)
            )
        )

    def test_parcela_unica_so_no_mes_ancora(self) -> None:
        self.assertTrue(
            parcela_prevista_na_competencia(
                anchor_month=date(2026, 5, 1), installment_count=1, competencia=date(2026, 5, 1)
            )
        )
        self.assertFalse(
            parcela_prevista_na_competencia(
                anchor_month=date(2026, 5, 1), installment_count=1, competencia=date(2026, 6, 1)
            )
        )


if __name__ == "__main__":
    unittest.main()
