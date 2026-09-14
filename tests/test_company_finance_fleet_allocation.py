"""Modo `fleet_allocation` ("Rateio pela frota") nos schemas de Custos Indiretos (puro, sem banco).

NULL = sem rateio; "LOCACAO" = fatura de locação (substitui o custo dos veículos);
"ADICIONAL" = custo adicional da frota (soma ao custo dos veículos).
"""

from __future__ import annotations

import unittest
from datetime import date

from pydantic import ValidationError

from app.models.company_finance import FLEET_ALLOCATION_ADDITIONAL, FLEET_ALLOCATION_RENTAL
from app.schemas.company_finance import (
    CompanyFinancialItemCreate,
    CompanyFinancialItemUpdate,
)


def _create(**extra) -> CompanyFinancialItemCreate:
    return CompanyFinancialItemCreate(
        tipo="custo_fixo",
        nome="Movida - Locação Frota",
        valor_referencia=1000.0,
        cost_center_ref="ADMINISTRATIVO",
        start_date=date(2026, 1, 1),
        **extra,
    )


class TestFleetAllocationSchema(unittest.TestCase):
    def test_constantes_do_modelo(self) -> None:
        self.assertEqual(FLEET_ALLOCATION_RENTAL, "LOCACAO")
        self.assertEqual(FLEET_ALLOCATION_ADDITIONAL, "ADICIONAL")

    def test_create_padrao_none(self) -> None:
        self.assertIsNone(_create().fleet_allocation)

    def test_create_aceita_locacao_e_adicional(self) -> None:
        self.assertEqual(_create(fleet_allocation="LOCACAO").fleet_allocation, FLEET_ALLOCATION_RENTAL)
        self.assertEqual(_create(fleet_allocation="ADICIONAL").fleet_allocation, FLEET_ALLOCATION_ADDITIONAL)

    def test_create_rejeita_outros_valores(self) -> None:
        for invalid in ("locacao", "SEGURO", True, ""):
            with self.subTest(value=invalid), self.assertRaises(ValidationError):
                _create(fleet_allocation=invalid)

    def test_update_nao_altera_quando_ausente(self) -> None:
        patch = CompanyFinancialItemUpdate().model_dump(exclude_unset=True)
        self.assertNotIn("fleet_allocation", patch)

    def test_update_envia_quando_informado(self) -> None:
        for mode in ("LOCACAO", "ADICIONAL"):
            with self.subTest(mode=mode):
                patch = CompanyFinancialItemUpdate(fleet_allocation=mode).model_dump(exclude_unset=True)
                self.assertEqual(patch.get("fleet_allocation"), mode)

    def test_update_null_explicito_limpa(self) -> None:
        patch = CompanyFinancialItemUpdate.model_validate({"fleet_allocation": None}).model_dump(exclude_unset=True)
        self.assertIn("fleet_allocation", patch)
        self.assertIsNone(patch["fleet_allocation"])

    def test_update_rejeita_outros_valores(self) -> None:
        with self.assertRaises(ValidationError):
            CompanyFinancialItemUpdate(fleet_allocation="OUTRO")


if __name__ == "__main__":
    unittest.main()
