"""Testes unitários das regras puras de ROI Operacional (sem banco)."""

from __future__ import annotations

import unittest

from app.services.indicators_service import aggregate_consolidado, compute_roi, sort_roi_desc


class TestComputeRoi(unittest.TestCase):
    def test_roi_positivo(self) -> None:
        # lucro 100k sobre custo 220k => ~0.4545
        self.assertAlmostEqual(compute_roi(100_000.0, 220_000.0), 100_000.0 / 220_000.0)

    def test_roi_negativo(self) -> None:
        self.assertAlmostEqual(compute_roi(-40_000.0, 484_000.0), -40_000.0 / 484_000.0)

    def test_roi_exato(self) -> None:
        self.assertEqual(compute_roi(50.0, 100.0), 0.5)

    def test_custo_zero_retorna_none(self) -> None:
        self.assertIsNone(compute_roi(10_000.0, 0.0))

    def test_custo_negativo_retorna_none(self) -> None:
        # custo não-positivo => indefinido (None), nunca 0
        self.assertIsNone(compute_roi(10_000.0, -5.0))

    def test_lucro_zero_custo_positivo_e_zero_nao_none(self) -> None:
        roi = compute_roi(0.0, 100.0)
        self.assertEqual(roi, 0.0)
        self.assertIsNotNone(roi)


class TestSortRoiDesc(unittest.TestCase):
    def test_ordena_maior_para_menor(self) -> None:
        items = [
            {"project_name": "C", "roi": 0.21},
            {"project_name": "A", "roi": 0.45},
            {"project_name": "B", "roi": 0.38},
        ]
        ordered = [i["project_name"] for i in sort_roi_desc(items)]
        self.assertEqual(ordered, ["A", "B", "C"])

    def test_none_vai_para_o_fim(self) -> None:
        items = [
            {"project_name": "SemCusto", "roi": None},
            {"project_name": "Alto", "roi": 0.5},
            {"project_name": "Negativo", "roi": -0.1},
        ]
        ordered = [i["project_name"] for i in sort_roi_desc(items)]
        self.assertEqual(ordered, ["Alto", "Negativo", "SemCusto"])

    def test_multiplos_none_preservam_estabilidade(self) -> None:
        items = [
            {"project_name": "N1", "roi": None},
            {"project_name": "X", "roi": 0.1},
            {"project_name": "N2", "roi": None},
        ]
        ordered = [i["project_name"] for i in sort_roi_desc(items)]
        self.assertEqual(ordered, ["X", "N1", "N2"])

    def test_lista_vazia(self) -> None:
        self.assertEqual(sort_roi_desc([]), [])


class TestAggregateConsolidado(unittest.TestCase):
    def test_consolidado_e_razao_das_somas_nao_media(self) -> None:
        rows = [
            {"revenue": 440511.77, "cost": 331971.9963, "operational_profit": 108539.7737},
            {"revenue": 88937.9, "cost": 73873.233, "operational_profit": 15064.667},
            {"revenue": 65240.0, "cost": 79044.70672, "operational_profit": -13804.70672},
        ]
        agg = aggregate_consolidado(rows)
        soma_cost = 331971.9963 + 73873.233 + 79044.70672
        soma_profit = 108539.7737 + 15064.667 - 13804.70672
        self.assertAlmostEqual(agg["cost"], soma_cost)
        self.assertAlmostEqual(agg["operational_profit"], soma_profit)
        self.assertAlmostEqual(agg["roi"], soma_profit / soma_cost)
        self.assertEqual(agg["project_count"], 3)

    def test_consolidado_difere_da_media_dos_rois(self) -> None:
        rows = [
            {"revenue": 100.0, "cost": 100.0, "operational_profit": 50.0},  # roi 0.5
            {"revenue": 100.0, "cost": 900.0, "operational_profit": 90.0},  # roi 0.1
        ]
        agg = aggregate_consolidado(rows)
        media_rois = (0.5 + 0.1) / 2  # 0.3 — PROIBIDO
        correto = 140.0 / 1000.0  # 0.14 — Σlucro/Σcusto
        self.assertAlmostEqual(agg["roi"], correto)
        self.assertNotAlmostEqual(agg["roi"], media_rois)

    def test_consolidado_custo_zero_roi_none(self) -> None:
        rows = [{"revenue": 0.0, "cost": 0.0, "operational_profit": 0.0}]
        agg = aggregate_consolidado(rows)
        self.assertIsNone(agg["roi"])
        self.assertIsNone(agg["roi_pct"])

    def test_consolidado_vazio(self) -> None:
        agg = aggregate_consolidado([])
        self.assertEqual(agg["project_count"], 0)
        self.assertEqual(agg["cost"], 0.0)
        self.assertIsNone(agg["roi"])


class TestRangeAccumulationSemantics(unittest.TestCase):
    """A acumulação de intervalo deve consolidar como Σlucro/Σcusto do período."""

    def test_acumulado_dois_meses_e_razao_das_somas(self) -> None:
        # mês 1: lucro 50 / custo 100 ; mês 2: lucro 90 / custo 900
        meses = [
            {"revenue": 100.0, "cost": 100.0, "operational_profit": 50.0},
            {"revenue": 100.0, "cost": 900.0, "operational_profit": 90.0},
        ]
        agg = aggregate_consolidado(meses)
        self.assertAlmostEqual(agg["cost"], 1000.0)
        self.assertAlmostEqual(agg["operational_profit"], 140.0)
        self.assertAlmostEqual(agg["roi"], 140.0 / 1000.0)  # 0.14, não média (0.30)

    def test_mes_unico_equivale_ao_proprio_mes(self) -> None:
        mes = [{"revenue": 440511.77, "cost": 331971.9963, "operational_profit": 108539.7737}]
        agg = aggregate_consolidado(mes)
        self.assertAlmostEqual(agg["roi"], 108539.7737 / 331971.9963)


if __name__ == "__main__":
    unittest.main()
