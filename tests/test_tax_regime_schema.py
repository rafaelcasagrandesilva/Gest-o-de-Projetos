"""Regime tributário: normalização dos parâmetros e das vigências (sem banco)."""

from __future__ import annotations

import asyncio
import unittest
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from pydantic import ValidationError

from app.models.tax_regime import TaxRegimePeriod
from app.schemas.settings import (
    FRACTION_RATE_FIELDS,
    SystemSettingsUpdate,
    TaxRegimePeriodCreate,
)
from app.services.tax_regime_service import TaxRegimeService, normalize_start_date

NEW_RATE_FIELDS = (
    "iss_rate",
    "pis_presumido_rate",
    "cofins_presumido_rate",
    "irpj_presumption_rate",
    "csll_presumption_rate",
    "irpj_rate",
    "irpj_additional_rate",
    "csll_rate",
    "pis_real_rate",
    "cofins_real_rate",
    "pis_cofins_credit_rate",
)


class SettingsRateNormalizationTests(unittest.TestCase):
    def test_all_new_rates_are_normalized(self) -> None:
        for name in NEW_RATE_FIELDS:
            self.assertIn(name, FRACTION_RATE_FIELDS)

    def test_integer_percent_becomes_fraction(self) -> None:
        upd = SystemSettingsUpdate(iss_rate=5, irpj_rate=15, csll_presumption_rate=32)
        self.assertAlmostEqual(upd.iss_rate, 0.05)
        self.assertAlmostEqual(upd.irpj_rate, 0.15)
        self.assertAlmostEqual(upd.csll_presumption_rate, 0.32)

    def test_fraction_kept(self) -> None:
        upd = SystemSettingsUpdate(pis_presumido_rate=0.0065, cofins_real_rate=0.076)
        self.assertAlmostEqual(upd.pis_presumido_rate, 0.0065)
        self.assertAlmostEqual(upd.cofins_real_rate, 0.076)

    def test_threshold_is_money_not_rate(self) -> None:
        self.assertNotIn("irpj_additional_monthly_threshold", FRACTION_RATE_FIELDS)
        upd = SystemSettingsUpdate(irpj_additional_monthly_threshold=20000)
        self.assertEqual(upd.irpj_additional_monthly_threshold, 20000)

    def test_invalid_fraction_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            SystemSettingsUpdate(pis_real_rate=1.5)
        with self.assertRaises(ValidationError):
            SystemSettingsUpdate(iss_rate=-0.01)


class TaxRegimePeriodCreateTests(unittest.TestCase):
    def test_regime_literal(self) -> None:
        TaxRegimePeriodCreate(regime="LUCRO_REAL", start_date=date(2026, 1, 1))
        with self.assertRaises(ValidationError):
            TaxRegimePeriodCreate(regime="SIMPLES", start_date=date(2026, 1, 1))

    def test_note_max_length(self) -> None:
        with self.assertRaises(ValidationError):
            TaxRegimePeriodCreate(regime="LUCRO_REAL", start_date=date(2026, 1, 1), note="x" * 256)


def _session_with_count(count: int) -> MagicMock:
    result = MagicMock()
    result.scalar_one.return_value = count
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


class TaxRegimeServiceTests(unittest.TestCase):
    def test_normalize_start_date(self) -> None:
        self.assertEqual(normalize_start_date(date(2026, 9, 14)), date(2026, 9, 1))

    def test_create_normalizes_to_first_of_month(self) -> None:
        db = _session_with_count(0)
        row = asyncio.run(
            TaxRegimeService(db).create_period(
                {"regime": "LUCRO_REAL", "start_date": date(2026, 10, 20), "note": "  "}
            )
        )
        self.assertEqual(row.start_date, date(2026, 10, 1))
        self.assertEqual(row.regime, "LUCRO_REAL")
        self.assertIsNone(row.note)
        db.add.assert_called_once()

    def test_create_duplicate_month_rejected(self) -> None:
        db = _session_with_count(1)
        with self.assertRaises(ValueError):
            asyncio.run(
                TaxRegimeService(db).create_period(
                    {"regime": "LUCRO_REAL", "start_date": date(2026, 10, 20)}
                )
            )
        db.add.assert_not_called()

    def test_delete_missing_returns_false(self) -> None:
        db = _session_with_count(2)
        db.get = AsyncMock(return_value=None)
        self.assertFalse(asyncio.run(TaxRegimeService(db).delete_period(MagicMock())))

    def test_delete_last_period_rejected(self) -> None:
        db = _session_with_count(1)
        db.get = AsyncMock(return_value=TaxRegimePeriod(regime="LUCRO_PRESUMIDO"))
        with self.assertRaises(ValueError):
            asyncio.run(TaxRegimeService(db).delete_period(MagicMock()))
        db.delete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
