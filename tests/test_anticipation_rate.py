"""Regra da taxa de antecipação do motor financeiro (pura, sem banco).

Automático, um mês à frente: o mês trabalhado M recebe o custo real das operações de M+1
(Lepta + Daycoval, sem repasse) ÷ receita de M; mês ainda sem operações/previsto usa a média
ponderada dos pares fechados; sem histórico cai no percentual fixo. Fixo: como antes.
"""

from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace

from app.core.scenario import Scenario
from app.services.anticipation_rate import (
    MODE_AUTOMATICO,
    MODE_FIXO,
    SOURCE_FIXA,
    SOURCE_MEDIA,
    SOURCE_PARCIAL,
    SOURCE_REAL,
    batch_advanced_and_cost,
    resolve_anticipation_rate,
)

DEZ = date(2025, 12, 1)
JAN, FEV, MAR, ABR, MAI, JUN, JUL = (date(2026, m, 1) for m in range(1, 8))

# Custo por mês da OPERAÇÃO: fevereiro antecipa o trabalho de janeiro, abril o de março.
COSTS = {FEV: 10_000.0, ABR: 30_000.0}
# Receita por mês TRABALHADO.
REVENUE = {JAN: 100_000.0, FEV: 150_000.0, MAR: 200_000.0, ABR: 50_000.0}


def rate(comp, *, scenario=Scenario.REALIZADO, mode=MODE_AUTOMATICO, current=MAI, costs=COSTS, revenue=REVENUE):
    return resolve_anticipation_rate(
        mode=mode,
        fixed_rate=0.24,
        competencia=comp,
        scenario=scenario,
        current_month=current,
        monthly_cost=costs,
        monthly_revenue=revenue,
    )


class ResolveAnticipationRateTests(unittest.TestCase):
    def test_modo_fixo_mantem_o_percentual(self) -> None:
        r = rate(MAR, mode=MODE_FIXO)
        self.assertEqual((r.rate, r.source), (0.24, SOURCE_FIXA))

    def test_mes_trabalhado_usa_o_custo_das_operacoes_do_mes_seguinte(self) -> None:
        r = rate(MAR)
        self.assertEqual(r.source, SOURCE_REAL)
        self.assertAlmostEqual(r.rate, 0.15)  # operações de abril (30 mil) ÷ receita de março (200 mil)

    def test_mes_seguinte_encerrado_sem_operacao_nao_tem_custo(self) -> None:
        r = rate(FEV)  # março terminou sem nenhuma antecipação
        self.assertEqual((r.rate, r.source), (0.0, SOURCE_REAL))

    def test_mes_seguinte_em_curso_com_operacoes_e_parcial(self) -> None:
        r = rate(ABR, costs={**COSTS, MAI: 5_000.0})
        self.assertEqual(r.source, SOURCE_PARCIAL)
        self.assertAlmostEqual(r.rate, 0.10)  # 5 mil de maio ÷ 50 mil de abril

    def test_mes_seguinte_em_curso_sem_operacao_ainda_usa_a_media(self) -> None:
        self.assertEqual(rate(ABR).source, SOURCE_MEDIA)

    def test_futuro_usa_media_ponderada_dos_pares_fechados(self) -> None:
        r = rate(JUN, costs={**COSTS, MAI: 5_000.0})  # o par abril→maio ainda não fechou
        self.assertEqual(r.source, SOURCE_MEDIA)
        self.assertAlmostEqual(r.rate, 40_000 / 300_000)  # ponderada, não a média simples de 10% e 15%

    def test_previsto_sempre_usa_a_media_anterior(self) -> None:
        r = rate(MAR, scenario=Scenario.PREVISTO)
        self.assertEqual(r.source, SOURCE_MEDIA)
        self.assertAlmostEqual(r.rate, 0.10)  # só o par janeiro→fevereiro vem antes de março

    def test_par_sem_receita_lancada_nao_entra_na_media(self) -> None:
        costs = {**COSTS, MAI: 50_000.0}
        revenue = {**REVENUE, ABR: 0.0}
        r = rate(JUL, costs=costs, revenue=revenue, current=JUL)
        self.assertAlmostEqual(r.rate, 40_000 / 300_000)

    def test_sem_historico_cai_no_percentual_fixo(self) -> None:
        self.assertEqual(rate(JAN, scenario=Scenario.PREVISTO).source, SOURCE_FIXA)
        r = rate(date(2025, 11, 1))  # dezembro, antes da primeira antecipação
        self.assertEqual((r.rate, r.source), (0.24, SOURCE_FIXA))
        self.assertEqual(rate(DEZ, revenue={**REVENUE, DEZ: 0.0}).source, SOURCE_FIXA)


class InstitutionSplitTests(unittest.TestCase):
    INST = {FEV: {"Lepta": 8_000.0, "Daycoval": 2_000.0}, ABR: {"Lepta": 15_000.0, "Daycoval": 15_000.0}}

    def test_mes_real_divide_pelas_operacoes_do_mes_seguinte(self) -> None:
        r = resolve_anticipation_rate(
            mode=MODE_AUTOMATICO, fixed_rate=0.24, competencia=JAN, scenario=Scenario.REALIZADO,
            current_month=MAI, monthly_cost=COSTS, monthly_revenue=REVENUE, cost_by_institution=self.INST,
        )
        self.assertEqual(r.source, SOURCE_REAL)
        self.assertEqual(r.split, (("Lepta", 0.8), ("Daycoval", 0.2)))

    def test_media_divide_pela_soma_dos_pares_fechados(self) -> None:
        r = resolve_anticipation_rate(
            mode=MODE_AUTOMATICO, fixed_rate=0.24, competencia=JUN, scenario=Scenario.REALIZADO,
            current_month=MAI, monthly_cost=COSTS, monthly_revenue=REVENUE, cost_by_institution=self.INST,
        )
        self.assertEqual(r.source, SOURCE_MEDIA)
        split = dict(r.split)
        self.assertAlmostEqual(split["Lepta"], 23_000 / 40_000)
        self.assertAlmostEqual(split["Daycoval"], 17_000 / 40_000)

    def test_fixo_nao_divide(self) -> None:
        r = rate(MAR, mode=MODE_FIXO)
        self.assertEqual(r.split, ())


class BatchCostTests(unittest.TestCase):
    def test_custo_e_cedido_menos_creditado_sem_repasse(self) -> None:
        batch = SimpleNamespace(
            items=[SimpleNamespace(advanced_amount=60_000), SimpleNamespace(advanced_amount=40_000)],
            received_amount=90_000,
            discount_amount=8_000,
            fee_amount=500,
            repasse_amount=7_000,
        )
        self.assertEqual(batch_advanced_and_cost(batch), (100_000.0, 10_000.0))

    def test_operacao_antiga_sem_valor_cedido_usa_o_fallback(self) -> None:
        batch = SimpleNamespace(
            items=[SimpleNamespace(advanced_amount=None)],
            received_amount=90_000,
            discount_amount=8_000,
            fee_amount=500,
        )
        self.assertEqual(batch_advanced_and_cost(batch), (98_500.0, 8_500.0))


if __name__ == "__main__":
    unittest.main()
