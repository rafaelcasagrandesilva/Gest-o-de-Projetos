"""Tributos por regime: Presumido × Real, vigência por competência e adicional de IRPJ (puro)."""

from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace

from app.services.tax_calc import (
    LUCRO_PRESUMIDO,
    LUCRO_REAL,
    profit_taxes_real,
    regime_for_competencia,
    revenue_taxes,
)

SETTINGS = SimpleNamespace(tax_rate=0.09)  # demais parâmetros nos padrões do módulo


class RegimePeriodTests(unittest.TestCase):
    PERIODS = [(date(2020, 1, 1), LUCRO_PRESUMIDO), (date(2026, 10, 15), LUCRO_REAL)]

    def test_vale_o_periodo_mais_recente_ate_a_competencia(self) -> None:
        self.assertEqual(regime_for_competencia(self.PERIODS, date(2026, 9, 1)), LUCRO_PRESUMIDO)
        self.assertEqual(regime_for_competencia(self.PERIODS, date(2026, 10, 1)), LUCRO_REAL)  # mudança vale no mês
        self.assertEqual(regime_for_competencia(self.PERIODS, date(2027, 1, 1)), LUCRO_REAL)

    def test_sem_periodo_usa_reserva(self) -> None:
        self.assertIsNone(regime_for_competencia([], date(2026, 9, 1)))
        taxes = revenue_taxes(regime=None, settings=SETTINGS, revenue=100_000, company_revenue=100_000)
        self.assertAlmostEqual(taxes.total, 9_000)


class PresumidoTests(unittest.TestCase):
    def test_empresa_sem_adicional(self) -> None:
        # base presumida 32% × 50 mil = 16 mil < limite de 20 mil → sem adicional
        t = revenue_taxes(regime=LUCRO_PRESUMIDO, settings=SETTINGS, revenue=50_000, company_revenue=50_000)
        self.assertAlmostEqual(t.pis, 325)
        self.assertAlmostEqual(t.cofins, 1_500)
        self.assertAlmostEqual(t.iss, 2_500)
        self.assertAlmostEqual(t.irpj, 2_400)  # 50 mil × 32% × 15%
        self.assertAlmostEqual(t.csll, 1_440)  # 50 mil × 32% × 9%
        self.assertAlmostEqual(t.total / 50_000, 0.1633)

    def test_adicional_da_empresa_repartido_pela_receita(self) -> None:
        empresa = revenue_taxes(regime=LUCRO_PRESUMIDO, settings=SETTINGS, revenue=880_000, company_revenue=880_000)
        adicional = (880_000 * 0.32 - 20_000) * 0.10
        self.assertAlmostEqual(empresa.irpj, 880_000 * 0.32 * 0.15 + adicional)
        projeto = revenue_taxes(regime=LUCRO_PRESUMIDO, settings=SETTINGS, revenue=220_000, company_revenue=880_000)
        self.assertAlmostEqual(projeto.irpj, 220_000 * 0.32 * 0.15 + adicional * 0.25)


class RealTests(unittest.TestCase):
    def test_receita_so_tem_pis_cofins_iss_com_creditos(self) -> None:
        t = revenue_taxes(regime=LUCRO_REAL, settings=SETTINGS, revenue=100_000, company_revenue=100_000)
        self.assertAlmostEqual((t.pis, t.cofins, t.iss, t.irpj, t.csll), (1_650, 7_600, 5_000, 0, 0))
        com_credito = SimpleNamespace(tax_rate=0.09, pis_cofins_credit_rate=0.0185)
        t2 = revenue_taxes(regime=LUCRO_REAL, settings=com_credito, revenue=100_000, company_revenue=100_000)
        self.assertAlmostEqual(t2.pis + t2.cofins, 9_250 - 1_850)

    def test_ir_csll_sobre_o_lucro_e_zero_no_prejuizo(self) -> None:
        self.assertEqual(profit_taxes_real(settings=SETTINGS, taxable_profit=-50_000), (0.0, 0.0))
        irpj, csll = profit_taxes_real(settings=SETTINGS, taxable_profit=100_000)
        self.assertAlmostEqual(irpj, 15_000 + 8_000)  # 15% + 10% sobre o que passa de 20 mil
        self.assertAlmostEqual(csll, 9_000)


if __name__ == "__main__":
    unittest.main()
