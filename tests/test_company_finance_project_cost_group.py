"""`project_cost_group` ("Entra no projeto como") nos schemas de Custos Indiretos (puro, sem banco).

NULL = Fixos operacionais (padrão); "MAO_DE_OBRA" / "VEICULOS" / "SISTEMAS" / "FIXOS" = custo raiz
do projeto em que o item (centro de custo = projeto) soma.
"""

from __future__ import annotations

import unittest
from datetime import date

from pydantic import ValidationError

from app.models.company_finance import (
    PROJECT_COST_GROUP_FIXED,
    PROJECT_COST_GROUP_LABOR,
    PROJECT_COST_GROUP_SYSTEMS,
    PROJECT_COST_GROUP_VEHICLES,
)
from app.schemas.company_finance import (
    CompanyFinancialItemCreate,
    CompanyFinancialItemRead,
    CompanyFinancialItemUpdate,
)

GROUPS = ("MAO_DE_OBRA", "VEICULOS", "SISTEMAS", "FIXOS")


def _create(**extra) -> CompanyFinancialItemCreate:
    return CompanyFinancialItemCreate(
        tipo="custo_fixo",
        nome="TICKET SOLUÇÕES - SUBTERRÂNEO",
        valor_referencia=1000.0,
        cost_center_ref="ADMINISTRATIVO",
        start_date=date(2026, 1, 1),
        **extra,
    )


class TestProjectCostGroupSchema(unittest.TestCase):
    def test_constantes_do_modelo(self) -> None:
        self.assertEqual(PROJECT_COST_GROUP_LABOR, "MAO_DE_OBRA")
        self.assertEqual(PROJECT_COST_GROUP_VEHICLES, "VEICULOS")
        self.assertEqual(PROJECT_COST_GROUP_SYSTEMS, "SISTEMAS")
        self.assertEqual(PROJECT_COST_GROUP_FIXED, "FIXOS")

    def test_create_padrao_none(self) -> None:
        self.assertIsNone(_create().project_cost_group)

    def test_create_aceita_os_quatro_grupos(self) -> None:
        for group in GROUPS:
            with self.subTest(group=group):
                self.assertEqual(_create(project_cost_group=group).project_cost_group, group)

    def test_create_rejeita_outros_valores(self) -> None:
        for invalid in ("veiculos", "Mão de obra", "LOCACAO", True, ""):
            with self.subTest(value=invalid), self.assertRaises(ValidationError):
                _create(project_cost_group=invalid)

    def test_update_nao_altera_quando_ausente(self) -> None:
        patch = CompanyFinancialItemUpdate().model_dump(exclude_unset=True)
        self.assertNotIn("project_cost_group", patch)

    def test_update_envia_quando_informado(self) -> None:
        for group in GROUPS:
            with self.subTest(group=group):
                patch = CompanyFinancialItemUpdate(project_cost_group=group).model_dump(exclude_unset=True)
                self.assertEqual(patch.get("project_cost_group"), group)

    def test_update_null_explicito_limpa(self) -> None:
        patch = CompanyFinancialItemUpdate.model_validate({"project_cost_group": None}).model_dump(
            exclude_unset=True
        )
        self.assertIn("project_cost_group", patch)
        self.assertIsNone(patch["project_cost_group"])

    def test_update_rejeita_outros_valores(self) -> None:
        with self.assertRaises(ValidationError):
            CompanyFinancialItemUpdate(project_cost_group="OUTRO")

    def test_read_padrao_none(self) -> None:
        self.assertIsNone(CompanyFinancialItemRead.model_fields["project_cost_group"].default)


if __name__ == "__main__":
    unittest.main()
