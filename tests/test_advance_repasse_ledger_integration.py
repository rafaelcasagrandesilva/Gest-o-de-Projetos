"""Fase 1B — integração Repasse → Ledger + reversão simétrica.

Valida a mudança de comportamento: o Repasse deixa o CAP e vira crédito no Ledger, com estorno
automático no cancelamento/edição (criar→crédito / cancelar→estorno, SEM resíduo). Deságio/tarifa
continuam no CAP. Testes de banco NÃO commitam (rollback ao final).
"""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from uuid import uuid4

TODAY = date(2026, 8, 6)
FUTURE = date(2026, 12, 1)


class _Base(unittest.IsolatedAsyncioTestCase):
    async def _prelude(self, s):
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        for t in ("advance_repasse_ledger", "advance_settlement_movements"):
            try:
                await s.execute(text(f"SELECT 1 FROM {t} LIMIT 1"))
            except ProgrammingError:
                self.skipTest(f"Tabela {t} ausente (rode alembic upgrade head).")

    async def _lepta(self, s):
        # Instituição LEPTA NOVA a cada teste → saldo do Ledger isolado (rollback), sem misturar
        # com os créditos reais do backfill.
        from app.models.advance_institution import AdvanceInstitution

        inst = AdvanceInstitution(
            name=f"LEPTA Teste {uuid4().hex[:10]}", institution_type="FACTORING",
            operation_profile="LEPTA", is_active=True,
        )
        s.add(inst)
        await s.flush()
        return inst

    async def _confirm_batch(self, s, *, inst, gross=100_000.0, discount=0.0, fee=0.0, repasse=True):
        from app.models.project import Project
        from app.models.receivable import ReceivableInvoice
        from app.services.receivable_advance_batch_service import ReceivableAdvanceBatchService

        project = Project(name=f"1B {uuid4().hex[:8]}", is_active=True)
        s.add(project)
        await s.flush()
        inv = ReceivableInvoice(
            nf_number=f"B-{uuid4().hex[:6]}", project_id=project.id,
            issue_date=date(2026, 5, 1), due_days=30, due_date=date(2026, 6, 1),
            gross_amount=gross, net_amount=gross, received_amount=0.0, invoice_status="EMITIDA",
        )
        s.add(inv)
        await s.flush()
        svc = ReceivableAdvanceBatchService(s)
        batch = await svc.create_batch(
            institution_id=inst.id, received_amount=gross, discount_amount=discount, fee_amount=fee,
            repasse_enabled=repasse, receive_date=date(2026, 6, 10), repayment_date=FUTURE,
            observation=None, invoice_ids=[inv.id], created_by_id=None,
        )
        await svc.confirm_batch(batch_id=batch.id)
        await s.flush()
        return svc, batch, inv


class RepasseLedgerIntegrationTests(_Base):
    async def test_confirm_credits_ledger_not_cap(self) -> None:
        from sqlalchemy import select
        from app.database.session import AsyncSessionLocal, engine
        from app.models.payable_snapshot import PayableSnapshot
        from app.services.advance_repasse_ledger_service import AdvanceRepasseLedgerService

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                inst = await self._lepta(s)
                svc, batch, _ = await self._confirm_batch(s, inst=inst, gross=100_000.0)
                # Repasse = 7% do antecipado (100k) = 7.000
                self.assertEqual(Decimal(str(batch.repasse_amount)), Decimal("7000.00"))
                led = AdvanceRepasseLedgerService(s)
                self.assertEqual(await led.balance(inst.id), Decimal("7000.00"))
                self.assertEqual(await led.active_credit_total(source_batch_id=batch.id), Decimal("7000.00"))
                # CAP NÃO tem linha de repasse deste lote
                rows = (await s.execute(select(PayableSnapshot).where(PayableSnapshot.ref_id == batch.id))).scalars().all()
                self.assertFalse(any("Repasse" in (r.name or "") for r in rows))
            finally:
                await s.rollback()

    async def test_cancel_reverses_credit_no_residue(self) -> None:
        """CICLO EXIGIDO: criar → crédito no Ledger → cancelar → estorno automático, sem resíduo."""
        from sqlalchemy import select
        from app.database.session import AsyncSessionLocal, engine
        from app.models.advance_repasse_ledger import AdvanceRepasseLedgerEntry
        from app.services.advance_repasse_ledger_service import AdvanceRepasseLedgerService

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                inst = await self._lepta(s)
                svc, batch, _ = await self._confirm_batch(s, inst=inst, gross=100_000.0)
                led = AdvanceRepasseLedgerService(s)
                self.assertEqual(await led.balance(inst.id), Decimal("7000.00"))

                await svc.cancel_batch(batch_id=batch.id)
                await s.flush()

                # Estorno automático: saldo 0, nenhum crédito ativo → SEM resíduo.
                self.assertEqual(await led.balance(inst.id), Decimal("0.00"))
                self.assertEqual(await led.active_credit_total(source_batch_id=batch.id), Decimal("0.00"))
                # Histórico preservado (append-only): o crédito continua existindo, porém estornado.
                entries = (
                    await s.execute(select(AdvanceRepasseLedgerEntry).where(AdvanceRepasseLedgerEntry.source_batch_id == batch.id))
                ).scalars().all()
                self.assertEqual(len(entries), 1)
                self.assertIsNotNone(entries[0].reversed_at)
            finally:
                await s.rollback()

    async def test_edit_recredits_ledger(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.advance_repasse_ledger_service import AdvanceRepasseLedgerService

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                inst = await self._lepta(s)
                svc, batch, inv = await self._confirm_batch(s, inst=inst, gross=100_000.0)
                led = AdvanceRepasseLedgerService(s)
                self.assertEqual(await led.balance(inst.id), Decimal("7000.00"))
                # Edita a base para LÍQUIDO−10% (advanced menor) → repasse recalculado (reverte→reaplica)
                await svc.edit_batch(
                    batch_id=batch.id, institution_id=inst.id, received_amount=100_000.0,
                    discount_amount=0.0, fee_amount=0.0, receive_date=date(2026, 6, 10),
                    repayment_date=FUTURE, observation=None,
                    items_config=[{"invoice_id": inv.id, "advance_basis": "LIQUIDO_MENOS_10"}],
                    repasse_enabled=True,
                )
                await s.flush()
                edited = await svc.get_batch(batch.id)
                expected = Decimal(str(round(float(edited.repasse_amount), 2)))
                # Só há UM crédito ativo, com o novo valor (o antigo foi estornado).
                self.assertEqual(await led.active_credit_total(source_batch_id=batch.id), expected)
                self.assertEqual(await led.balance(inst.id), expected)
            finally:
                await s.rollback()

    async def test_cancel_blocked_when_repasse_consumed(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.advance_repasse_ledger_service import AdvanceRepasseLedgerService
        from app.services.advance_settlement_service import AdvanceSettlementService

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                inst = await self._lepta(s)
                svc, batch, _ = await self._confirm_batch(s, inst=inst, gross=100_000.0)
                led = AdvanceRepasseLedgerService(s)
                self.assertEqual(await led.balance(inst.id), Decimal("7000.00"))
                # Consome o repasse liquidando a obrigação com SALDO_REPASSE.
                loaded = await svc.get_batch(batch.id)
                item_id = loaded.items[0].id
                sset = AdvanceSettlementService(s)
                await sset.add_movements(
                    batch_item_id=item_id, today=TODAY,
                    movements=[{"funding_source": "SALDO_REPASSE", "amount": 7_000.0}],
                )
                self.assertEqual(await led.balance(inst.id), Decimal("0.00"))
                # Cancelar agora deve ser BLOQUEADO (repasse já consumido).
                with self.assertRaises(ValueError):
                    await svc.cancel_batch(batch_id=batch.id)
            finally:
                await s.rollback()

    async def test_desagio_tarifa_still_in_cap(self) -> None:
        from sqlalchemy import select
        from app.database.session import AsyncSessionLocal, engine
        from app.models.payable_snapshot import PayableSnapshot

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                inst = await self._lepta(s)
                svc, batch, _ = await self._confirm_batch(s, inst=inst, gross=100_000.0, discount=5_000.0, fee=300.0)
                rows = (await s.execute(select(PayableSnapshot).where(PayableSnapshot.ref_id == batch.id))).scalars().all()
                names = [r.name for r in rows]
                self.assertTrue(any("Deságio" in (n or "") for n in names))
                self.assertTrue(any("Tarifas" in (n or "") for n in names))
                self.assertFalse(any("Repasse" in (n or "") for n in names))  # repasse saiu do CAP
            finally:
                await s.rollback()

    async def test_capability_drives_obligation_no_constant(self) -> None:
        import app.services.advance_settlement_service as mod
        from app.services.advance_settlement_service import profile_creates_obligation

        # A constante foi ELIMINADA — o comportamento vem da capacidade do handler.
        self.assertFalse(hasattr(mod, "SETTLEMENT_OBLIGATION_PROFILES"))
        self.assertTrue(profile_creates_obligation("LEPTA"))
        self.assertFalse(profile_creates_obligation("DAYCOVAL"))
        self.assertFalse(profile_creates_obligation(None))


if __name__ == "__main__":
    unittest.main()
