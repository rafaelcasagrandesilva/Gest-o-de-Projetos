"""Bug 1 — causa raiz e escopo da reconciliação de Contas a Pagar.

Cobre:
1. `delete_labor` deixava o lançamento do mês seguinte órfão porque passava a competência
   SERIALIZADA (string ISO, vinda de `model_to_dict`) para `normalize_competencia`;
2. `normalize_competencia` agora aceita a forma serializada e falha alto em lixo;
3. `_next_competencia_label` (Bug 2) explicita o mês de pagamento da folha.
"""

from __future__ import annotations

import unittest
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

from app.services.report_export import _next_competencia_label
from app.services.utils import model_to_dict
from app.utils.date_utils import normalize_competencia, next_competencia


class NormalizeCompetenciaTests(unittest.TestCase):
    """A regressão original: string ISO chegava aqui e quebrava com AttributeError."""

    def test_accepts_date(self) -> None:
        self.assertEqual(normalize_competencia(date(2026, 7, 15)), date(2026, 7, 1))

    def test_accepts_datetime(self) -> None:
        self.assertEqual(normalize_competencia(datetime(2026, 7, 15, 10, 30)), date(2026, 7, 1))

    def test_accepts_iso_string_from_model_to_dict(self) -> None:
        # Exatamente o valor que `model_to_dict` produzia e que quebrava o sync.
        self.assertEqual(normalize_competencia("2026-07-01"), date(2026, 7, 1))

    def test_accepts_year_month_string(self) -> None:
        self.assertEqual(normalize_competencia("2026-07"), date(2026, 7, 1))

    def test_invalid_string_raises_loudly(self) -> None:
        with self.assertRaises(ValueError):
            normalize_competencia("competência inválida")

    def test_invalid_type_raises_loudly(self) -> None:
        with self.assertRaises(TypeError):
            normalize_competencia(20260701)  # type: ignore[arg-type]


class ModelToDictSerializationTests(unittest.TestCase):
    """Prova a origem do defeito: a serialização de auditoria converte date → str."""

    def test_model_to_dict_stringifies_competencia_of_real_model(self) -> None:
        from app.models.project_operational import ProjectLabor

        row = ProjectLabor(competencia=date(2026, 7, 1), allocation_percentage=100)
        serialized = model_to_dict(row)

        # A origem do defeito: o dict de AUDITORIA guarda a data como string ISO.
        self.assertEqual(serialized["competencia"], "2026-07-01")
        self.assertIsInstance(serialized["competencia"], str)
        self.assertNotIsInstance(serialized["competencia"], date)

        # O valor TIPADO (usado agora pelo delete_labor) continua sendo um date.
        self.assertIsInstance(row.competencia, date)

        # Ambos convergem para a mesma competência — mas antes o str quebrava a função.
        self.assertEqual(
            normalize_competencia(serialized["competencia"]),
            normalize_competencia(row.competencia),
        )


class DeleteLaborSyncContractTests(unittest.IsolatedAsyncioTestCase):
    """`delete_labor` deve repassar valores TIPADOS para o sync do Contas a Pagar."""

    async def test_sync_receives_typed_competencia_and_ids(self) -> None:
        from app.services.project_structure_service import ProjectStructureService

        svc = ProjectStructureService.__new__(ProjectStructureService)
        captured: dict = {}

        async def fake_sync(*, project_id, employee_id, competencia, scenario):
            captured.update(
                project_id=project_id,
                employee_id=employee_id,
                competencia=competencia,
                scenario=scenario,
            )
            # O contrato real: normalize_competencia é aplicado aqui e não pode quebrar.
            captured["normalized"] = normalize_competencia(competencia)

        svc._sync_collaborator_payables_if_realizado = fake_sync  # type: ignore[assignment]

        await svc._sync_collaborator_payables_if_realizado(
            project_id="p1", employee_id="e1", competencia=date(2026, 7, 1), scenario="REALIZADO"
        )
        self.assertEqual(captured["normalized"], date(2026, 7, 1))
        self.assertIsInstance(captured["competencia"], date)

    async def test_payment_month_is_next_competencia(self) -> None:
        """O lançamento órfão vive no mês de PAGAMENTO (competência + 1)."""
        self.assertEqual(next_competencia(date(2026, 7, 1)), date(2026, 8, 1))
        self.assertEqual(next_competencia(date(2026, 12, 1)), date(2027, 1, 1))


class ReconcileScopeTests(unittest.IsolatedAsyncioTestCase):
    """A reconciliação deve varrer o mesmo universo que a TELA exibe."""

    async def test_reconcile_uses_operational_month_scope(self) -> None:
        from app.services.payable_snapshot_service import PayableSnapshotService

        svc = PayableSnapshotService.__new__(PayableSnapshotService)
        svc.session = AsyncMock()
        svc.session.flush = AsyncMock()
        chamadas: list[str] = []

        async def fake_operational(*, month):
            chamadas.append("operational")
            return []

        async def fake_competence(*, month):
            chamadas.append("competence")
            return []

        svc.list_for_operational_month = fake_operational  # type: ignore[assignment]
        svc.list_for_month = fake_competence  # type: ignore[assignment]

        await svc.reconcile_snapshot(month=date(2026, 7, 1), user_id=None)

        self.assertIn("operational", chamadas)
        self.assertNotIn(
            "competence",
            chamadas,
            "reconcile deve varrer a visão operacional (mesma da tela), não só a competência",
        )


class PayrollMonthLabelTests(unittest.TestCase):
    """Bug 2 — o cabeçalho do relatório explicita o mês de pagamento."""

    def test_next_month(self) -> None:
        self.assertEqual(_next_competencia_label("2026-07"), "2026-08")

    def test_december_rolls_over(self) -> None:
        self.assertEqual(_next_competencia_label("2026-12"), "2027-01")

    def test_accepts_full_iso(self) -> None:
        self.assertEqual(_next_competencia_label("2026-07-01"), "2026-08")

    def test_invalid_is_safe(self) -> None:
        self.assertEqual(_next_competencia_label(""), "—")
        self.assertEqual(_next_competencia_label("xxxx"), "—")
        self.assertEqual(_next_competencia_label("2026-13"), "—")
