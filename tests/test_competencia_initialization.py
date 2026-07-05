"""Testes das regras puras de Inicializar Competência (resolução de origem → destino)."""

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


class TestOriginTargetScenario(unittest.TestCase):
    def test_previous_and_current_realizado_target(self) -> None:
        self.assertEqual(InitializationOrigin.PREVIOUS_REALIZADO.target_scenario, Scenario.REALIZADO)
        self.assertEqual(InitializationOrigin.CURRENT_PREVISTO.target_scenario, Scenario.REALIZADO)

    def test_previous_previsto_target(self) -> None:
        self.assertEqual(InitializationOrigin.PREVIOUS_PREVISTO.target_scenario, Scenario.PREVISTO)


class TestResolveRefs(unittest.TestCase):
    def setUp(self) -> None:
        self.pid = uuid4()
        self.jul = date(2026, 7, 1)
        self.jun = date(2026, 6, 1)

    def test_realizado_da_competencia_anterior(self) -> None:
        # Junho (Realizado) → Julho (Realizado)
        src, tgt = CompetenciaInitializationService._resolve_refs(
            self.pid, self.jul, InitializationOrigin.PREVIOUS_REALIZADO
        )
        self.assertEqual((src.competencia, src.scenario), (self.jun, Scenario.REALIZADO))
        self.assertEqual((tgt.competencia, tgt.scenario), (self.jul, Scenario.REALIZADO))
        self.assertEqual(src.project_id, self.pid)

    def test_previsto_da_competencia_atual(self) -> None:
        # Julho (Previsto) → Julho (Realizado)
        src, tgt = CompetenciaInitializationService._resolve_refs(
            self.pid, self.jul, InitializationOrigin.CURRENT_PREVISTO
        )
        self.assertEqual((src.competencia, src.scenario), (self.jul, Scenario.PREVISTO))
        self.assertEqual((tgt.competencia, tgt.scenario), (self.jul, Scenario.REALIZADO))

    def test_previsto_da_competencia_anterior(self) -> None:
        # Junho (Previsto) → Julho (Previsto)
        src, tgt = CompetenciaInitializationService._resolve_refs(
            self.pid, self.jul, InitializationOrigin.PREVIOUS_PREVISTO
        )
        self.assertEqual((src.competencia, src.scenario), (self.jun, Scenario.PREVISTO))
        self.assertEqual((tgt.competencia, tgt.scenario), (self.jul, Scenario.PREVISTO))

    def test_cross_year_previous(self) -> None:
        # Janeiro/2026 → dezembro/2025 como anterior.
        src, tgt = CompetenciaInitializationService._resolve_refs(
            self.pid, date(2026, 1, 1), InitializationOrigin.PREVIOUS_PREVISTO
        )
        self.assertEqual(src.competencia, date(2025, 12, 1))
        self.assertEqual(tgt.competencia, date(2026, 1, 1))


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
