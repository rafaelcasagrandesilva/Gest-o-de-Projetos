"""Testes unitários da normalização de alias (sem dependências de banco)."""

from __future__ import annotations

import unittest


def _normalize_alias(value: str) -> str:
    """Cópia da regra de negócio para teste isolado (evita importar SQLAlchemy)."""
    return " ".join(str(value or "").strip().split()).casefold()


class TestNormalizeAlias(unittest.TestCase):
    def test_trim_lower_and_collapse_spaces(self) -> None:
        self.assertEqual(_normalize_alias("  Enel - Treinamento - SP  "), "enel - treinamento - sp")

    def test_empty(self) -> None:
        self.assertEqual(_normalize_alias(""), "")
        self.assertEqual(_normalize_alias("   "), "")

    def test_dedupe_key_stability(self) -> None:
        a = _normalize_alias("Enel X - Luminotécnico")
        b = _normalize_alias("enel x  -  luminotécnico")
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
