"""Antecipações: edição de operação ativa (reverter → aplicar → reaplicar) + criar já ativo.

Testes de banco NÃO commitam (rollback ao final) — não alteram dados reais.
"""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from uuid import uuid4

TODAY = date(2026, 8, 4)


class AdvanceBatchEditTests(unittest.IsolatedAsyncioTestCase):
    async def _prelude(self, session):
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        try:
            await session.execute(text("SELECT 1 FROM receivable_advance_batches LIMIT 1"))
        except ProgrammingError:
            self.skipTest("Tabela receivable_advance_batches ausente (rode alembic upgrade head).")

    async def _setup_invoices(self, session, *, n=2, gross=50_000.0):
        from app.models.project import Project
        from app.models.receivable import ReceivableInvoice

        project = Project(name=f"Teste edição borderô {uuid4().hex[:8]}", is_active=True)
        session.add(project)
        await session.flush()
        invs = []
        for i in range(n):
            inv = ReceivableInvoice(
                nf_number=f"E-{uuid4().hex[:6]}-{i}", project_id=project.id,
                issue_date=date(2026, 5, 1), due_days=30, due_date=date(2026, 6, 1),
                gross_amount=gross, net_amount=gross, received_amount=0.0, invoice_status="EMITIDA",
            )
            session.add(inv)
            invs.append(inv)
        await session.flush()
        return project, invs

    async def _bordero_titles(self, session, batch_id):
        from sqlalchemy import select
        from app.models.payable_snapshot import PayableSnapshot

        # As despesas do borderô (deságio/tarifa/repasse) têm ref_id = batch.id.
        return (
            await session.execute(
                select(PayableSnapshot).where(PayableSnapshot.ref_id == batch_id)
            )
        ).scalars().all()

    async def test_create_confirm_then_edit_keeps_cap_clean(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.models.receivable_advance_batch import ReceivableAdvanceBatchStatus
        from app.services.receivable_advance_batch_service import ReceivableAdvanceBatchService

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                _proj, (inv_a, inv_b) = await self._setup_invoices(s)
                svc = ReceivableAdvanceBatchService(s)
                batch = await svc.create_batch(
                    institution="LEPTA", received_amount=94_500.0, discount_amount=5_000.0,
                    fee_amount=500.0, receive_date=date(2026, 6, 10), repayment_date=date(2026, 7, 10),
                    observation=None, invoice_ids=[inv_a.id, inv_b.id], created_by_id=None,
                )
                await svc.confirm_batch(batch_id=batch.id)
                await s.flush()
                self.assertEqual(batch.status, ReceivableAdvanceBatchStatus.OPEN)
                # Deságio e tarifas já vêm descontados: nenhum título no Contas a Pagar.
                self.assertEqual(await self._bordero_titles(s, batch.id), [])
                # NFs marcadas como antecipadas.
                await s.refresh(inv_a)
                self.assertTrue(inv_a.is_anticipated)

                # EDITA: muda o deságio de 5.000 → 3.000 (reverte → aplica → reaplica).
                await svc.edit_batch(
                    batch_id=batch.id, institution="LEPTA", received_amount=94_500.0,
                    discount_amount=3_000.0, fee_amount=500.0, receive_date=date(2026, 6, 10),
                    repayment_date=date(2026, 7, 10), observation=None,
                    invoice_ids=[inv_a.id, inv_b.id],
                )
                await s.flush()
                edited = await svc.get_batch(batch.id)
                self.assertEqual(edited.status, ReceivableAdvanceBatchStatus.OPEN)
                self.assertEqual(float(edited.discount_amount), 3000.0)  # o custo fica na operação
                self.assertEqual(await self._bordero_titles(s, batch.id), [])  # CAP continua limpo
                self.assertEqual(len(edited.items), 2)  # itens remontados
            finally:
                await s.rollback()

    async def test_edit_removes_a_nf(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.receivable_advance_batch_service import ReceivableAdvanceBatchService

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                _proj, (inv_a, inv_b) = await self._setup_invoices(s)
                svc = ReceivableAdvanceBatchService(s)
                batch = await svc.create_batch(
                    institution="LEPTA", received_amount=90_000.0, discount_amount=1_000.0,
                    fee_amount=0.0, receive_date=date(2026, 6, 10), repayment_date=date(2026, 7, 10),
                    observation=None, invoice_ids=[inv_a.id, inv_b.id], created_by_id=None,
                )
                await svc.confirm_batch(batch_id=batch.id)
                await s.flush()
                # Edita removendo a NF B (fica só a A).
                await svc.edit_batch(
                    batch_id=batch.id, institution="LEPTA", received_amount=45_000.0,
                    discount_amount=1_000.0, fee_amount=0.0, receive_date=date(2026, 6, 10),
                    repayment_date=date(2026, 7, 10), observation=None, invoice_ids=[inv_a.id],
                )
                await s.flush()
                edited = await svc.get_batch(batch.id)
                self.assertEqual(len(edited.items), 1)
                self.assertEqual(edited.items[0].invoice_id, inv_a.id)
                # NF removida volta a não-antecipada (não está em outra operação).
                await s.refresh(inv_b)
                self.assertFalse(inv_b.is_anticipated)
            finally:
                await s.rollback()

    async def test_cancel_still_works_after_refactor(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.models.receivable_advance_batch import ReceivableAdvanceBatchStatus
        from app.services.receivable_advance_batch_service import ReceivableAdvanceBatchService

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                _proj, (inv_a, inv_b) = await self._setup_invoices(s)
                svc = ReceivableAdvanceBatchService(s)
                batch = await svc.create_batch(
                    institution="LEPTA", received_amount=94_500.0, discount_amount=5_000.0,
                    fee_amount=500.0, receive_date=date(2026, 6, 10), repayment_date=date(2026, 7, 10),
                    observation=None, invoice_ids=[inv_a.id, inv_b.id], created_by_id=None,
                )
                await svc.confirm_batch(batch_id=batch.id)
                await s.flush()
                await svc.cancel_batch(batch_id=batch.id)
                await s.flush()
                cancelled = await svc.get_batch(batch.id)
                self.assertEqual(cancelled.status, ReceivableAdvanceBatchStatus.CANCELLED)
                self.assertEqual(await self._bordero_titles(s, batch.id), [])  # CAP removido
                await s.refresh(inv_a)
                self.assertFalse(inv_a.is_anticipated)  # NF revertida
            finally:
                await s.rollback()
