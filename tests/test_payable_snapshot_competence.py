"""Testes de correção de competência em snapshots recorrentes."""

from __future__ import annotations

import unittest
from datetime import date

from app.utils.date_utils import next_competencia, normalize_competencia, previous_competencia


def _correct_bulk_project_snapshot_month(row_month: date, generation_months: list[date]) -> date | None:
    """Espelha a regra da migration 0060 para snapshots com tag de projeto."""
    row_comp = normalize_competencia(row_month)
    normalized_gens = [normalize_competencia(g) for g in generation_months]
    if row_comp in normalized_gens:
        return None
    for gen_comp in normalized_gens:
        if row_comp == previous_competencia(gen_comp) and row_comp != gen_comp:
            return gen_comp
    return None


class PayableSnapshotCompetenceFixTests(unittest.TestCase):
    def test_bulk_project_snapshot_shifted_one_month_forward(self) -> None:
        apr = date(2026, 4, 1)
        may = date(2026, 5, 1)
        fixed = _correct_bulk_project_snapshot_month(apr, [may])
        self.assertEqual(fixed, may)

    def test_dynamic_snapshot_not_shifted(self) -> None:
        mar = date(2026, 3, 1)
        apr = date(2026, 4, 1)
        fixed = _correct_bulk_project_snapshot_month(mar, [mar, apr])
        self.assertIsNone(fixed)

    def test_orphan_bulk_row_shifted_when_target_month_generated(self) -> None:
        apr = date(2026, 4, 1)
        may = date(2026, 5, 1)
        fixed = _correct_bulk_project_snapshot_month(apr, [may])
        self.assertEqual(fixed, may)

    def test_next_competencia_chain(self) -> None:
        jan = date(2026, 1, 1)
        self.assertEqual(next_competencia(jan), date(2026, 2, 1))
        self.assertEqual(previous_competencia(date(2026, 2, 1)), jan)


if __name__ == "__main__":
    unittest.main()
