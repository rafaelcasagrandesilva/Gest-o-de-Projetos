"""Borderô: deságio e tarifa persistem no CAP após invalidate/regeneração."""

from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.models.payable_snapshot import PayableSnapshotType
from app.services.receivable_advance_batch_service import (
    ReceivableAdvanceBatchService,
    _BATCH_DISCOUNT_SUFFIX,
    _BATCH_FEE_SUFFIX,
    _batch_payable_observation,
    _is_bordero_operation_payable,
)
from app.utils.date_utils import normalize_competencia


def _snapshot_row(*, name: str, observation: str, snap_type=PayableSnapshotType.MANUAL):
    row = MagicMock()
    row.name = name
    row.observation = observation
    row.type = snap_type
    row.amount_paid = 0
    return row


class BorderoPayableHelperTests(unittest.TestCase):
    def test_is_bordero_operation_payable_manual(self) -> None:
        row = _snapshot_row(
            name="LEPTA — Deságio",
            observation=_batch_payable_observation("10"),
            snap_type=PayableSnapshotType.MANUAL,
        )
        self.assertTrue(_is_bordero_operation_payable(row, operation_tag="10"))
        self.assertFalse(_is_bordero_operation_payable(row, operation_tag="99"))

    def test_is_bordero_operation_payable_legacy_antecipacao(self) -> None:
        row = _snapshot_row(
            name="LEPTA — Tarifas bancárias",
            observation=_batch_payable_observation("BT-2026-0001"),
            snap_type=PayableSnapshotType.ANTECIPACAO,
        )
        self.assertTrue(_is_bordero_operation_payable(row, operation_tag="BT-2026-0001"))


class BorderoPayablesAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_ensure_payables_uses_manual_type_and_idempotent(self) -> None:
        db = AsyncMock()
        svc = ReceivableAdvanceBatchService(db)
        receive = date(2026, 6, 15)
        existing_discount = _snapshot_row(
            name=f"LEPTA{_BATCH_DISCOUNT_SUFFIX}",
            observation=_batch_payable_observation("OP-TEST"),
        )

        with patch("app.services.receivable_advance_batch_service.PayableSnapshotService") as PS:
            payables = PS.return_value
            payables.is_generated = AsyncMock(return_value=True)
            payables.list_for_month = AsyncMock(return_value=[existing_discount])
            payables.create_manual = AsyncMock(return_value=MagicMock())

            await svc._ensure_payables_for_batch(
                batch_number="OP-TEST",
                institution="LEPTA",
                receive_date=receive,
                repayment_date=date(2026, 7, 15),
                discount_amount=5000.0,
                fee_amount=500.0,
            )

            self.assertEqual(payables.create_manual.await_count, 1)
            call = payables.create_manual.await_args
            self.assertIsNotNone(call)
            self.assertNotIn("snapshot_type", call.kwargs)
            self.assertEqual(call.kwargs["name"], f"LEPTA{_BATCH_FEE_SUFFIX}")
            self.assertEqual(call.kwargs["amount"], 500.0)
            self.assertEqual(call.kwargs["observation"], _batch_payable_observation("OP-TEST"))

    async def test_create_batch_payables_survive_invalidate_and_regenerate(self) -> None:
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        from app.database.session import AsyncSessionLocal
        from app.models.project import Project
        from app.models.receivable import ReceivableInvoice
        from app.services.payable_snapshot_service import PayableSnapshotService

        async with AsyncSessionLocal() as session:
            try:
                await session.execute(text("SELECT 1 FROM receivable_advance_batches LIMIT 1"))
            except ProgrammingError:
                self.skipTest("Tabela receivable_advance_batches ausente (rode alembic upgrade head).")

            project = Project(name=f"Teste borderô CAP {uuid4().hex[:8]}", is_active=True)
            session.add(project)
            await session.flush()

            inv_common = dict(
                project_id=project.id,
                issue_date=date(2026, 5, 1),
                due_days=30,
                due_date=date(2026, 6, 1),
                gross_amount=50_000.0,
                net_amount=50_000.0,
                received_amount=0.0,
                invoice_status="EMITIDA",
            )
            inv_a = ReceivableInvoice(nf_number=f"T-{uuid4().hex[:6]}-A", **inv_common)
            inv_b = ReceivableInvoice(nf_number=f"T-{uuid4().hex[:6]}-B", **inv_common)
            session.add(inv_a)
            session.add(inv_b)
            await session.flush()

            batch_svc = ReceivableAdvanceBatchService(session)
            receive = date(2026, 6, 10)
            comp = normalize_competencia(receive)

            batch = await batch_svc.create_batch(
                institution="LEPTA",
                received_amount=94_500.0,
                discount_amount=5_000.0,
                fee_amount=500.0,
                receive_date=receive,
                repayment_date=date(2026, 7, 10),
                observation=None,
                invoice_ids=[inv_a.id, inv_b.id],
                created_by_id=None,
            )
            await session.commit()

            tag = batch.operation_code or batch.batch_number
            payables = PayableSnapshotService(session)

            def _bordero_lines(rows: list) -> list:
                return [r for r in rows if _is_bordero_operation_payable(r, operation_tag=tag)]

            rows = _bordero_lines(await payables.list_for_month(month=comp))
            self.assertEqual(len(rows), 2)
            self.assertEqual(sorted(float(r.amount_original) for r in rows), [500.0, 5000.0])
            self.assertTrue(all(r.type == PayableSnapshotType.MANUAL for r in rows))

            await payables.invalidate_months(months={comp})
            for _ in range(10):
                await payables.get_or_create_for_month(
                    payment_month=comp,
                    sees_all_projects=True,
                    accessible_project_ids=None,
                )
            await payables.get_or_create_for_month(
                payment_month=comp,
                sees_all_projects=True,
                accessible_project_ids=None,
                force_regenerate=True,
            )
            await session.commit()

            rows_after = _bordero_lines(await payables.list_for_month(month=comp))
            self.assertEqual(len(rows_after), 2)
            self.assertEqual(sorted(float(r.amount_original) for r in rows_after), [500.0, 5000.0])

            await batch_svc._ensure_payables_for_batch(
                batch_number=tag,
                institution="LEPTA",
                receive_date=receive,
                repayment_date=date(2026, 7, 10),
                discount_amount=5_000.0,
                fee_amount=500.0,
            )
            await session.flush()
            rows_dup = _bordero_lines(await payables.list_for_month(month=comp))
            self.assertEqual(len(rows_dup), 2)

            await batch_svc.cancel_batch(batch_id=batch.id)
            await session.commit()


if __name__ == "__main__":
    unittest.main()
