"""Testes unitários das regras puras de ROI Operacional (sem banco)."""

from __future__ import annotations

import unittest

from datetime import date

from app.services.indicators_service import (
    IndicatorsService,
    aggregate_consolidado,
    compute_roi,
    growth_pct,
    is_economically_relevant,
    sort_roi_desc,
    trend_label,
)


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


class TestIsEconomicallyRelevant(unittest.TestCase):
    """Regra de elegibilidade: receita>0 OU custo>0 (com tolerância de meio centavo)."""

    def test_receita_e_custo_positivos_aparece(self) -> None:
        # Projeto A: receita 100k, custo 50k
        self.assertTrue(is_economically_relevant(100_000.0, 50_000.0))

    def test_so_custo_positivo_aparece(self) -> None:
        # Projeto B: receita 0, custo 30k (encerrado com custo ainda lançado)
        self.assertTrue(is_economically_relevant(0.0, 30_000.0))

    def test_so_receita_positiva_aparece(self) -> None:
        # Projeto D: encerrado com receita 20k, custo 10k -> mesmo só a receita basta
        self.assertTrue(is_economically_relevant(20_000.0, 0.0))

    def test_sem_receita_e_sem_custo_nao_aparece(self) -> None:
        # Projeto C: receita 0, custo 0 -> não elegível
        self.assertFalse(is_economically_relevant(0.0, 0.0))

    def test_valores_dentro_da_tolerancia_nao_aparecem(self) -> None:
        # Resíduos sub-centavo são tratados como zero.
        self.assertFalse(is_economically_relevant(0.004, 0.004))

    def test_valor_acima_da_tolerancia_aparece(self) -> None:
        self.assertTrue(is_economically_relevant(0.0, 0.01))


class TestAggregateConsolidadoExecutivo(unittest.TestCase):
    """Campos adicionais do Dashboard Executivo (Custos de M.O. e Lucro Líquido)."""

    def test_soma_labor_cost_veiculos_e_net_profit(self) -> None:
        rows = [
            {"revenue": 100.0, "cost": 60.0, "operational_profit": 40.0, "labor_cost": 25.0, "vehicle_cost": 5.0, "net_profit": 30.0},
            {"revenue": 200.0, "cost": 150.0, "operational_profit": 50.0, "labor_cost": 80.0, "vehicle_cost": 12.0, "net_profit": 45.0},
        ]
        agg = aggregate_consolidado(rows)
        self.assertAlmostEqual(agg["labor_cost"], 105.0)
        self.assertAlmostEqual(agg["vehicle_cost"], 17.0)
        self.assertAlmostEqual(agg["net_profit"], 75.0)

    def test_campos_ausentes_tratados_como_zero(self) -> None:
        # rows sem labor_cost/vehicle_cost/net_profit (compat. com o ROI atual) => 0.
        rows = [{"revenue": 100.0, "cost": 60.0, "operational_profit": 40.0}]
        agg = aggregate_consolidado(rows)
        self.assertEqual(agg["labor_cost"], 0.0)
        self.assertEqual(agg["vehicle_cost"], 0.0)
        self.assertEqual(agg["net_profit"], 0.0)


class TestGrowthPct(unittest.TestCase):
    def test_crescimento_positivo(self) -> None:
        # 280 -> 657 ≈ +134,6% (referência do protótipo)
        self.assertAlmostEqual(growth_pct(280.0, 657.0), (657.0 - 280.0) / 280.0 * 100.0)

    def test_base_zero_retorna_none(self) -> None:
        self.assertIsNone(growth_pct(0.0, 1000.0))

    def test_base_negativa_usa_modulo(self) -> None:
        # base -100 -> 0 é uma melhora de +100%.
        self.assertAlmostEqual(growth_pct(-100.0, 0.0), 100.0)


class TestTrendLabel(unittest.TestCase):
    def test_alta(self) -> None:
        self.assertEqual(trend_label(100.0, 150.0), "alta")

    def test_baixa(self) -> None:
        self.assertEqual(trend_label(150.0, 100.0), "baixa")

    def test_estavel_dentro_da_tolerancia(self) -> None:
        self.assertEqual(trend_label(100.0, 100.0), "estavel")


class TestBuildKpis(unittest.TestCase):
    def test_total_acumulado_e_crescimento(self) -> None:
        points = [
            {"faturamento": 100.0, "custo_mo": 40.0, "lucro_operacional": 20.0, "lucro_liquido": 10.0},
            {"faturamento": 200.0, "custo_mo": 60.0, "lucro_operacional": 50.0, "lucro_liquido": 40.0},
        ]
        kpis = IndicatorsService._build_kpis(points)
        self.assertAlmostEqual(kpis["faturamento"]["total"], 300.0)
        self.assertAlmostEqual(kpis["faturamento"]["growth_pct"], 100.0)  # 100 -> 200
        self.assertAlmostEqual(kpis["lucro_liquido"]["total"], 50.0)


class TestBuildInsights(unittest.TestCase):
    def test_extremos_e_ranking_de_projetos(self) -> None:
        points = [
            {"competencia": date(2026, 1, 1), "faturamento": 100.0, "custo_mo": 40.0, "lucro_operacional": 20.0, "lucro_liquido": 5.0},
            {"competencia": date(2026, 2, 1), "faturamento": 300.0, "custo_mo": 90.0, "lucro_operacional": 80.0, "lucro_liquido": 60.0},
            {"competencia": date(2026, 3, 1), "faturamento": 200.0, "custo_mo": 70.0, "lucro_operacional": 40.0, "lucro_liquido": -10.0},
        ]
        proj_totals = [
            {"project_id": "a", "project_name": "Alpha", "revenue": 400.0, "operational_profit": 90.0},
            {"project_id": "b", "project_name": "Beta", "revenue": 200.0, "operational_profit": 50.0},
        ]
        ins = IndicatorsService._build_insights(points, proj_totals)
        self.assertEqual(ins["maior_faturamento"]["value"], 300.0)
        self.assertEqual(ins["maior_faturamento"]["competencia"], date(2026, 2, 1))
        self.assertEqual(ins["menor_faturamento"]["value"], 100.0)
        self.assertEqual(ins["maior_lucro_liquido"]["value"], 60.0)
        self.assertEqual(ins["projeto_maior_faturamento"]["project_name"], "Alpha")
        self.assertEqual(ins["tendencia"], "alta")  # 100 -> 200
        self.assertAlmostEqual(ins["crescimento_acumulado_pct"], 100.0)

    def test_series_vazia_nao_quebra(self) -> None:
        ins = IndicatorsService._build_insights([], [])
        self.assertIsNone(ins["maior_faturamento"])
        self.assertIsNone(ins["projeto_maior_faturamento"])
        self.assertEqual(ins["tendencia"], "estavel")


if __name__ == "__main__":
    unittest.main()
