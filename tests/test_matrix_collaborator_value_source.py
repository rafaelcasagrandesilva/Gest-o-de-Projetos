"""Custo fixo de colaborador: o valor vem do CADASTRO, não da coluna do item.

Um item COLABORADOR_MATRIZ guarda `valor_referencia`, mas nenhuma leitura usa: card, KPI,
pendências e Contas a Pagar recalculam a partir do colaborador (salário/custo PJ × percentual).
Essa duplicidade já causou um bug de silêncio — a tela oferecia o campo para edição, salvava na
coluna e continuava exibindo o valor derivado, como se nada tivesse acontecido.

O teste fixa qual das duas fontes manda.
"""

from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace


def _item(*, valor_referencia: float, percentual: float, employee) -> SimpleNamespace:
    from app.models.company_finance import CompanyFinancialItemType

    return SimpleNamespace(
        tipo="custo_fixo",
        item_type=CompanyFinancialItemType.COLABORADOR_MATRIZ,
        employee=employee,
        percentual=percentual,
        valor_referencia=valor_referencia,
    )


class MatrixCollaboratorValueSourceTests(unittest.TestCase):
    def test_contas_a_pagar_usa_o_cadastro_e_ignora_a_coluna(self) -> None:
        from app.services.payable_snapshot_service import PayableSnapshotService

        pj = SimpleNamespace(
            employment_type="PJ", salary_base=3700.0, pj_hours_per_month=None, pj_additional_cost=0.0
        )
        # A coluna diz 2.500 (valor antigo); o cadastro diz 3.700. Vence o cadastro.
        item = _item(valor_referencia=2500.0, percentual=100.0, employee=pj)

        valor = PayableSnapshotService._company_finance_monthly_value(
            None, item, comp=date(2026, 9, 1), settings=SimpleNamespace()
        )
        self.assertEqual(float(valor), 3700.0)

    def test_percentual_rateia_o_valor_do_cadastro(self) -> None:
        """Meio período no centro de custo → metade do custo do colaborador."""
        from app.services.payable_snapshot_service import PayableSnapshotService

        pj = SimpleNamespace(
            employment_type="PJ", salary_base=3700.0, pj_hours_per_month=None, pj_additional_cost=0.0
        )
        item = _item(valor_referencia=999_999.0, percentual=50.0, employee=pj)

        valor = PayableSnapshotService._company_finance_monthly_value(
            None, item, comp=date(2026, 9, 1), settings=SimpleNamespace()
        )
        self.assertEqual(float(valor), 1850.0)

    def test_custo_fixo_comum_continua_usando_a_coluna(self) -> None:
        """O contraponto: sem colaborador vinculado, a coluna é a fonte legítima."""
        from app.services.payable_snapshot_service import PayableSnapshotService

        item = SimpleNamespace(
            tipo="custo_fixo", item_type=None, employee=None, percentual=None, valor_referencia=1234.56
        )
        valor = PayableSnapshotService._company_finance_monthly_value(
            None, item, comp=date(2026, 9, 1), settings=SimpleNamespace()
        )
        self.assertEqual(float(valor), 1234.56)


if __name__ == "__main__":
    unittest.main()
