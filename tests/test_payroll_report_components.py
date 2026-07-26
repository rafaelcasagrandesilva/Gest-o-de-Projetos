"""Regra de negócio: o relatório de folha usa a MESMA classificação da tela do CAP.

O relatório consolida os lançamentos do Contas a Pagar exibidos como "Colaborador"
(COLLABORATOR ou FIXED_COST categoria "Colaborador") + Endividamento, por construção.
Nenhuma reconstrução de valor; nenhuma heurística de nome.
"""

from __future__ import annotations

import unittest

from app.models.payable_snapshot import PayableSnapshotType
from app.services.payable_display import (
    COLLABORATOR_GROUP,
    ENDIVIDAMENTO_GROUP,
    is_collaborator_payroll,
    is_employee_debt,
    payable_display_group,
)


class DisplayGroupTests(unittest.TestCase):
    """A classificação espelha exatamente a tela do CAP (Payables.tsx)."""

    def test_collaborator_type_is_folha(self) -> None:
        self.assertTrue(is_collaborator_payroll(type_=PayableSnapshotType.COLLABORATOR, category="Mão de obra"))

    def test_fixed_cost_categoria_colaborador_is_folha(self) -> None:
        # Caso Rafael: salário vindo do cadastro de custo fixo vinculado ao colaborador.
        self.assertTrue(is_collaborator_payroll(type_=PayableSnapshotType.FIXED_COST, category="Colaborador"))

    def test_fixed_cost_custos_diversos_is_NOT_folha(self) -> None:
        # Caso João (2026-05/06): FIXED_COST "Custos diversos" NÃO é folha (tela: "Custo diverso").
        self.assertFalse(is_collaborator_payroll(type_=PayableSnapshotType.FIXED_COST, category="Custos diversos"))
        self.assertEqual(
            payable_display_group(type_=PayableSnapshotType.FIXED_COST, category="Custos diversos"),
            "Custo diverso",
        )

    def test_fixed_cost_custo_fixo_is_NOT_folha(self) -> None:
        self.assertFalse(is_collaborator_payroll(type_=PayableSnapshotType.FIXED_COST, category="Custo Fixo"))
        self.assertEqual(
            payable_display_group(type_=PayableSnapshotType.FIXED_COST, category="Custo Fixo"), "Custo Fixo"
        )

    def test_manual_is_NOT_folha(self) -> None:
        # Caso João (2026-01): MANUAL "João (Salário)" NÃO é folha (tela: "Manual").
        self.assertFalse(is_collaborator_payroll(type_=PayableSnapshotType.MANUAL, category="Prestação de Serviços"))
        self.assertEqual(
            payable_display_group(type_=PayableSnapshotType.MANUAL, category="qualquer"), "Manual"
        )

    def test_endividamento_is_debt_not_folha(self) -> None:
        self.assertTrue(is_employee_debt(type_=PayableSnapshotType.ENDIVIDAMENTO, category="Endividamento"))
        self.assertFalse(is_collaborator_payroll(type_=PayableSnapshotType.ENDIVIDAMENTO, category="Endividamento"))

    def test_financial_legacy_maps_to_endividamento(self) -> None:
        self.assertEqual(
            payable_display_group(type_=PayableSnapshotType.FINANCIAL, category=None), ENDIVIDAMENTO_GROUP
        )

    def test_vehicle_and_antecipacao_not_folha(self) -> None:
        self.assertEqual(payable_display_group(type_=PayableSnapshotType.VEHICLE, category=None), "Veículos")
        self.assertEqual(
            payable_display_group(type_=PayableSnapshotType.ANTECIPACAO_OPERACAO, category=None), "Antecipação"
        )

    def test_group_constants(self) -> None:
        self.assertEqual(COLLABORATOR_GROUP, "Colaborador")
        self.assertEqual(ENDIVIDAMENTO_GROUP, "Endividamento")
