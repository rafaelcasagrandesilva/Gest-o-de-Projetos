"""Testes das regras puras de Inicializar Competência (resolução de origem → destino).

O destino é o cenário em que o usuário está trabalhando, NÃO uma dedução da origem: quem monta
o Previsto a partir do realizado do mês anterior precisa que a cópia caia no Previsto.
"""

from __future__ import annotations

import unittest
from datetime import date
from uuid import uuid4

from app.core.scenario import Scenario
from app.services.competencia_initialization_service import (
    CATEGORY_LABELS,
    CompetenciaInitializationService,
    CostCategory,
    InitializationOrigin,
)


class TestLegacyTargetScenario(unittest.TestCase):
    """Padrão para chamadas que não informam o destino — preserva o comportamento anterior."""

    def test_previous_and_current_realizado_target(self) -> None:
        self.assertEqual(InitializationOrigin.PREVIOUS_REALIZADO.legacy_target_scenario, Scenario.REALIZADO)
        self.assertEqual(InitializationOrigin.CURRENT_PREVISTO.legacy_target_scenario, Scenario.REALIZADO)

    def test_previous_previsto_target(self) -> None:
        self.assertEqual(InitializationOrigin.PREVIOUS_PREVISTO.legacy_target_scenario, Scenario.PREVISTO)


class TestResolveRefs(unittest.TestCase):
    def setUp(self) -> None:
        self.pid = uuid4()
        self.jul = date(2026, 7, 1)
        self.jun = date(2026, 6, 1)

    def test_realizado_da_competencia_anterior(self) -> None:
        # Junho (Realizado) → Julho (Realizado)
        src, tgt = CompetenciaInitializationService.resolve_refs(
            self.pid, self.jul, InitializationOrigin.PREVIOUS_REALIZADO
        )
        self.assertEqual((src.competencia, src.scenario), (self.jun, Scenario.REALIZADO))
        self.assertEqual((tgt.competencia, tgt.scenario), (self.jul, Scenario.REALIZADO))
        self.assertEqual(src.project_id, self.pid)

    def test_previsto_da_competencia_atual(self) -> None:
        # Julho (Previsto) → Julho (Realizado)
        src, tgt = CompetenciaInitializationService.resolve_refs(
            self.pid, self.jul, InitializationOrigin.CURRENT_PREVISTO
        )
        self.assertEqual((src.competencia, src.scenario), (self.jul, Scenario.PREVISTO))
        self.assertEqual((tgt.competencia, tgt.scenario), (self.jul, Scenario.REALIZADO))

    def test_previsto_da_competencia_anterior(self) -> None:
        # Junho (Previsto) → Julho (Previsto)
        src, tgt = CompetenciaInitializationService.resolve_refs(
            self.pid, self.jul, InitializationOrigin.PREVIOUS_PREVISTO
        )
        self.assertEqual((src.competencia, src.scenario), (self.jun, Scenario.PREVISTO))
        self.assertEqual((tgt.competencia, tgt.scenario), (self.jul, Scenario.PREVISTO))

    def test_cross_year_previous(self) -> None:
        # Janeiro/2026 → dezembro/2025 como anterior.
        src, tgt = CompetenciaInitializationService.resolve_refs(
            self.pid, date(2026, 1, 1), InitializationOrigin.PREVIOUS_PREVISTO
        )
        self.assertEqual(src.competencia, date(2025, 12, 1))
        self.assertEqual(tgt.competencia, date(2026, 1, 1))


class TestTargetScenarioExplicito(unittest.TestCase):
    """O destino informado manda — é a correção do bug relatado."""

    def setUp(self) -> None:
        self.pid = uuid4()
        self.jul = date(2026, 7, 1)
        self.jun = date(2026, 6, 1)

    def test_realizado_anterior_para_previsto(self) -> None:
        # O caso do bug: montar o Previsto de julho com o Realizado de junho.
        # Antes isto gravava em REALIZADO, sobrescrevendo o realizado de julho.
        src, tgt = CompetenciaInitializationService.resolve_refs(
            self.pid, self.jul, InitializationOrigin.PREVIOUS_REALIZADO, Scenario.PREVISTO
        )
        self.assertEqual((src.competencia, src.scenario), (self.jun, Scenario.REALIZADO))
        self.assertEqual((tgt.competencia, tgt.scenario), (self.jul, Scenario.PREVISTO))

    def test_previsto_anterior_para_realizado(self) -> None:
        src, tgt = CompetenciaInitializationService.resolve_refs(
            self.pid, self.jul, InitializationOrigin.PREVIOUS_PREVISTO, Scenario.REALIZADO
        )
        self.assertEqual((src.competencia, src.scenario), (self.jun, Scenario.PREVISTO))
        self.assertEqual((tgt.competencia, tgt.scenario), (self.jul, Scenario.REALIZADO))

    def test_origem_igual_ao_destino_e_recusada(self) -> None:
        # "Previsto da competência atual" com destino PREVISTO copiaria o conjunto sobre
        # si mesmo — e como a cópia SUBSTITUI, apagaria tudo antes de recopiar.
        with self.assertRaises(ValueError):
            CompetenciaInitializationService.resolve_refs(
                self.pid, self.jul, InitializationOrigin.CURRENT_PREVISTO, Scenario.PREVISTO
            )


class TestCategoryMetadata(unittest.TestCase):
    def test_all_categories_have_plural_label(self) -> None:
        for cat in CostCategory:
            self.assertIn(cat, CATEGORY_LABELS)
            self.assertTrue(CATEGORY_LABELS[cat])

    def test_labels_match_ui(self) -> None:
        self.assertEqual(CATEGORY_LABELS[CostCategory.LABOR], "colaboradores")
        self.assertEqual(CATEGORY_LABELS[CostCategory.VEHICLES], "veículos")
        self.assertEqual(CATEGORY_LABELS[CostCategory.SYSTEMS], "sistemas")
        self.assertEqual(CATEGORY_LABELS[CostCategory.MISC], "custos diversos")


if __name__ == "__main__":
    unittest.main()
