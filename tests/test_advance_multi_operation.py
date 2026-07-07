"""Arquitetura N:N: uma mesma NF pode participar de várias operações de antecipação.

Valida a regra central da evolução do módulo de Antecipações (1 NF → N operações),
preservando o histórico e sem quebrar recebimento/dashboard.
"""

from __future__ import annotations

import unittest
from datetime import date
from uuid import uuid4

from app.services.receivable_advance_batch_service import ReceivableAdvanceBatchService


class AdvanceMultiOperationTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_invoice_in_multiple_operations(self) -> None:
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        from app.database.session import AsyncSessionLocal, engine

        # O engine assíncrono é criado no import e fica atrelado ao primeiro event loop.
        # Como cada IsolatedAsyncioTestCase roda em seu próprio loop, descartamos o pool
        # para reabrir conexões no loop atual (evita "Event loop is closed" na suíte).
        await engine.dispose()

        from app.models.project import Project
        from app.models.receivable import ReceivableInvoice

        async with AsyncSessionLocal() as session:
            try:
                await session.execute(text("SELECT 1 FROM receivable_advance_batches LIMIT 1"))
            except ProgrammingError:
                self.skipTest("Tabela receivable_advance_batches ausente (rode alembic upgrade head).")

            project = Project(name=f"Teste N:N {uuid4().hex[:8]}", is_active=True)
            session.add(project)
            await session.flush()

            inv = ReceivableInvoice(
                nf_number=f"NN-{uuid4().hex[:6]}",
                project_id=project.id,
                issue_date=date(2026, 5, 1),
                due_days=30,
                due_date=date(2026, 6, 1),
                gross_amount=40_000.0,
                net_amount=40_000.0,
                received_amount=0.0,
                invoice_status="EMITIDA",
            )
            session.add(inv)
            await session.flush()

            batch_svc = ReceivableAdvanceBatchService(session)

            # 1ª operação: cria + confirma. NF vira ANTECIPADA.
            b1 = await batch_svc.create_batch(
                institution="LEPTA",
                received_amount=38_000.0,
                receive_date=date(2026, 6, 10),
                repayment_date=date(2026, 7, 10),
                observation=None,
                invoice_ids=[inv.id],
                created_by_id=None,
            )
            await batch_svc.confirm_batch(batch_id=b1.id)
            await session.flush()

            await session.refresh(inv)
            self.assertTrue(inv.is_anticipated)
            self.assertEqual(inv.advance_batch_id, b1.id)

            # Regra 3: a NF já antecipada CONTINUA elegível para novas operações.
            eligible_ids = {
                r.id for r in await batch_svc.list_eligible_invoices(project_ids=[project.id])
            }
            self.assertIn(inv.id, eligible_ids)

            # Regra 1/2: adicionar a MESMA NF a uma 2ª operação NÃO deve levantar erro.
            b2 = await batch_svc.create_batch(
                institution="LEPTA",
                received_amount=37_000.0,
                receive_date=date(2026, 6, 20),
                repayment_date=date(2026, 7, 20),
                observation=None,
                invoice_ids=[inv.id],
                created_by_id=None,
            )
            await batch_svc.confirm_batch(batch_id=b2.id)
            await session.flush()

            # Regra 7/8: contador considera apenas operações confirmadas válidas.
            counts = await batch_svc.confirmed_operation_counts([inv.id])
            self.assertEqual(counts.get(inv.id), 2)

            # Regra 5: histórico lista TODAS as operações relacionadas.
            history = await batch_svc.invoice_operation_history(inv.id)
            self.assertEqual(len(history), 2)
            self.assertEqual({h["id"] for h in history}, {b1.id, b2.id})

            # Ponteiro denormalizado aponta para a operação confirmada mais recente.
            await session.refresh(inv)
            self.assertEqual(inv.advance_batch_id, b2.id)

            # Cancelar a operação mais recente: a NF permanece ANTECIPADA (ainda há b1),
            # e o ponteiro é recomposto para a operação válida remanescente.
            await batch_svc.cancel_batch(batch_id=b2.id)
            await session.flush()
            await session.refresh(inv)
            self.assertTrue(inv.is_anticipated)
            self.assertEqual(inv.advance_batch_id, b1.id)
            counts = await batch_svc.confirmed_operation_counts([inv.id])
            self.assertEqual(counts.get(inv.id), 1)

            # Cancelar também b1: sem operações válidas, a NF volta a EMITIDA.
            await batch_svc.cancel_batch(batch_id=b1.id)
            await session.flush()
            await session.refresh(inv)
            self.assertFalse(inv.is_anticipated)
            self.assertIsNone(inv.advance_batch_id)
            self.assertEqual(inv.invoice_status, "EMITIDA")

            # Limpeza: remove definitivamente operações canceladas + projeto/NF.
            await batch_svc.delete_batch(batch_id=b2.id)
            await batch_svc.delete_batch(batch_id=b1.id)
            await session.delete(inv)
            await session.delete(project)
            await session.commit()


if __name__ == "__main__":
    unittest.main()
