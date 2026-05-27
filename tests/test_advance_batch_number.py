"""Testes de numeração de borderô."""

from __future__ import annotations

import unittest

from app.services.receivable_advance_batch_service import _next_batch_number


class AdvanceBatchNumberTests(unittest.TestCase):
    def test_first_of_year(self) -> None:
        self.assertEqual(_next_batch_number([], year=2026), "BT-2026-0001")

    def test_increments(self) -> None:
        existing = ["BT-2026-0001", "BT-2026-0002"]
        self.assertEqual(_next_batch_number(existing, year=2026), "BT-2026-0003")


if __name__ == "__main__":
    unittest.main()
