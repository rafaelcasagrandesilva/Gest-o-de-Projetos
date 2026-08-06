"""Fase 1A — Liquidação de NFs + Ledger de Repasse (infraestrutura DORMENTE).

Exercita a infra isoladamente (o Ledger é semeado direto nos testes, pois a 1A não integra o
fluxo da LEPTA). Testes de banco NÃO commitam (rollback ao final) — não alteram dados reais.
"""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from uuid import uuid4

TODAY = date(2026, 8, 6)
FUTURE = date(2026, 12, 1)
PAST = date(2026, 7, 1)


class _Base(unittest.IsolatedAsyncioTestCase):
    async def _prelude(self, s):
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        for t in ("advance_settlement_movements", "advance_repasse_ledger"):
            try:
                await s.execute(text(f"SELECT 1 FROM {t} LIMIT 1"))
            except ProgrammingError:
                self.skipTest(f"Tabela {t} ausente (rode alembic upgrade head).")

    async def _lepta(self, s):
        # Instituição LEPTA NOVA a cada teste → saldo do Ledger isolado (rollback ao final),
        # sem misturar com os créditos reais do backfill (institução "Lepta Multissetorial").
        from app.models.advance_institution import AdvanceInstitution

        inst = AdvanceInstitution(
            name=f"LEPTA Teste {uuid4().hex[:10]}", institution_type="FACTORING",
            operation_profile="LEPTA", is_active=True,
        )
        s.add(inst)
        await s.flush()
        return inst

    async def _make_obligations(self, s, *, gross=100_000.0, repayment=FUTURE, n=1, inst=None, due_date=FUTURE):
        """Cria uma operação LEPTA confirmada com N NFs → N obrigações (participações)."""
        from app.models.project import Project
        from app.models.receivable import ReceivableInvoice
        from app.services.receivable_advance_batch_service import ReceivableAdvanceBatchService

        inst = inst or await self._lepta(s)
        project = Project(name=f"Liq {uuid4().hex[:8]}", is_active=True)
        s.add(project)
        await s.flush()
        invs = []
        for i in range(n):
            inv = ReceivableInvoice(
                nf_number=f"L-{uuid4().hex[:6]}-{i}", project_id=project.id,
                issue_date=date(2026, 5, 1), due_days=30, due_date=due_date,
                gross_amount=gross, net_amount=gross, received_amount=0.0,
                client_name=f"Cliente {i}", invoice_status="EMITIDA",
            )
            s.add(inv)
            invs.append(inv)
        await s.flush()
        svc = ReceivableAdvanceBatchService(s)
        # repasse_enabled=False: estes testes semeiam o Ledger manualmente; a obrigação existe
        # independentemente do repasse (capacidade do handler, não do flag).
        batch = await svc.create_batch(
            institution_id=inst.id, received_amount=gross, discount_amount=0.0, fee_amount=0.0,
            repasse_enabled=False, receive_date=date(2026, 6, 10), repayment_date=repayment,
            observation=None, invoice_ids=[iv.id for iv in invs], created_by_id=None,
        )
        await svc.confirm_batch(batch_id=batch.id)
        await s.flush()
        loaded = await svc.get_batch(batch.id)
        return inst, batch, list(loaded.items), invs


class LedgerServiceTests(_Base):
    async def test_credit_debit_balance_reverse(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.models.advance_repasse_ledger import RepasseLedgerSource
        from app.models.advance_settlement_movement import AdvanceFundingSource, AdvanceSettlementMovement
        from app.services.advance_repasse_ledger_service import AdvanceRepasseLedgerService

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                inst, batch, items, _ = await self._make_obligations(s, gross=100_000.0)
                item = items[0]
                led = AdvanceRepasseLedgerService(s)
                self.assertEqual(await led.balance(inst.id), Decimal("0.00"))
                await led.credit(institution_id=inst.id, amount=1000, source_type=RepasseLedgerSource.OPERATION, occurred_at=TODAY, source_batch_id=batch.id)
                await led.credit(institution_id=inst.id, amount=500, source_type=RepasseLedgerSource.OPERATION, occurred_at=TODAY, source_batch_id=batch.id)
                self.assertEqual(await led.balance(inst.id), Decimal("1500.00"))
                # Débito ligado a uma movimentação REAL (FK exige existência).
                mv = AdvanceSettlementMovement(
                    batch_item_id=item.id, batch_id=batch.id, invoice_id=item.invoice_id,
                    institution_id=inst.id, amount=Decimal("300.00"),
                    funding_source=AdvanceFundingSource.SALDO_REPASSE, settled_at=TODAY,
                )
                s.add(mv)
                await s.flush()
                await led.debit(institution_id=inst.id, amount=300, source_type=RepasseLedgerSource.SETTLEMENT, occurred_at=TODAY, source_movement_id=mv.id)
                self.assertEqual(await led.balance(inst.id), Decimal("1200.00"))
                # estorno do débito → volta ao saldo anterior
                n = await led.reverse_source(source_movement_id=mv.id, reason="teste")
                self.assertEqual(n, 1)
                self.assertEqual(await led.balance(inst.id), Decimal("1500.00"))
                # valor não positivo é rejeitado
                with self.assertRaises(ValueError):
                    await led.credit(institution_id=inst.id, amount=0, source_type=RepasseLedgerSource.OPERATION, occurred_at=TODAY)
            finally:
                await s.rollback()


class SettlementServiceTests(_Base):
    async def test_partial_then_complete_and_situacao(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.advance_settlement_service import (
            AdvanceSettlementService, EM_ABERTO, PARCIALMENTE_LIQUIDADA, LIQUIDADA,
        )

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                inst, batch, items, _ = await self._make_obligations(s, gross=100_000.0)
                item = items[0]
                svc = AdvanceSettlementService(s)

                obs = await svc.list_obligations(today=TODAY)
                mine = [o for o in obs if o["batch_item_id"] == item.id]
                self.assertEqual(len(mine), 1)
                o = mine[0]
                self.assertEqual(o["valor_total"], 100_000.0)
                self.assertEqual(o["valor_liquidado"], 0.0)
                self.assertEqual(o["situacao"], EM_ABERTO)
                self.assertEqual(o["origens_resumo"], "")

                # Liquida parcialmente (Caixa 40k) → PARCIALMENTE_LIQUIDADA, residual 60k
                o = await svc.add_movements(
                    batch_item_id=item.id, today=TODAY,
                    movements=[{"funding_source": "CAIXA_EMPRESA", "amount": 40_000.0, "settled_at": TODAY}],
                )
                self.assertEqual(o["valor_liquidado"], 40_000.0)
                self.assertEqual(o["valor_residual"], 60_000.0)
                self.assertEqual(o["situacao"], PARCIALMENTE_LIQUIDADA)
                self.assertEqual(o["origens_resumo"], "Caixa")

                # Completa (Cliente 60k) → LIQUIDADA, residual 0
                o = await svc.add_movements(
                    batch_item_id=item.id, today=TODAY,
                    movements=[{"funding_source": "RECEBIMENTO_CLIENTE", "amount": 60_000.0, "settled_at": TODAY}],
                )
                self.assertEqual(o["valor_residual"], 0.0)
                self.assertEqual(o["situacao"], LIQUIDADA)
                self.assertEqual(set(o["origens_resumo"].split(" + ")), {"Caixa", "Cliente"})
            finally:
                await s.rollback()

    async def test_multi_origin_only_repasse_debits_ledger(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.models.advance_repasse_ledger import RepasseLedgerSource
        from app.services.advance_repasse_ledger_service import AdvanceRepasseLedgerService
        from app.services.advance_settlement_service import AdvanceSettlementService, LIQUIDADA

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                inst, batch, items, _ = await self._make_obligations(s, gross=100_000.0)
                item = items[0]
                led = AdvanceRepasseLedgerService(s)
                # Semeia saldo de repasse (na 1A não há crédito automático de operação)
                await led.credit(institution_id=inst.id, amount=30_000.0, source_type=RepasseLedgerSource.OPERATION, occurred_at=TODAY)
                self.assertEqual(await led.balance(inst.id), Decimal("30000.00"))

                svc = AdvanceSettlementService(s)
                o = await svc.add_movements(
                    batch_item_id=item.id, today=TODAY,
                    movements=[
                        {"funding_source": "SALDO_REPASSE", "amount": 30_000.0},
                        {"funding_source": "CAIXA_EMPRESA", "amount": 20_000.0},
                        {"funding_source": "ANTECIPACAO_DAYCOVAL", "amount": 50_000.0},
                    ],
                )
                self.assertEqual(o["situacao"], LIQUIDADA)
                self.assertEqual(set(o["origens_resumo"].split(" + ")), {"Repasse", "Caixa", "Daycoval"})
                # Só a parcela de Repasse debitou o ledger → saldo 0
                self.assertEqual(await led.balance(inst.id), Decimal("0.00"))
            finally:
                await s.rollback()

    async def test_guard_over_settlement(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.advance_settlement_service import AdvanceSettlementService

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                _inst, _batch, items, _ = await self._make_obligations(s, gross=50_000.0)
                svc = AdvanceSettlementService(s)
                with self.assertRaises(ValueError):
                    await svc.add_movements(
                        batch_item_id=items[0].id, today=TODAY,
                        movements=[{"funding_source": "CAIXA_EMPRESA", "amount": 50_001.0}],
                    )
            finally:
                await s.rollback()

    async def test_guard_repasse_balance_but_other_source_ok(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.advance_settlement_service import AdvanceSettlementService

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                _inst, _batch, items, _ = await self._make_obligations(s, gross=100_000.0)
                svc = AdvanceSettlementService(s)
                # Saldo de repasse = 0 → parcela SALDO_REPASSE é bloqueada
                with self.assertRaises(ValueError):
                    await svc.add_movements(
                        batch_item_id=items[0].id, today=TODAY,
                        movements=[{"funding_source": "SALDO_REPASSE", "amount": 10_000.0}],
                    )
                # ... mas a liquidação por outra origem NÃO é impedida
                o = await svc.add_movements(
                    batch_item_id=items[0].id, today=TODAY,
                    movements=[{"funding_source": "CAIXA_EMPRESA", "amount": 10_000.0}],
                )
                self.assertEqual(o["valor_liquidado"], 10_000.0)
            finally:
                await s.rollback()

    async def test_reverse_movement_reopens_and_reverses_ledger(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.models.advance_repasse_ledger import RepasseLedgerSource
        from app.services.advance_repasse_ledger_service import AdvanceRepasseLedgerService
        from app.services.advance_settlement_service import AdvanceSettlementService, EM_ABERTO

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                inst, _batch, items, _ = await self._make_obligations(s, gross=100_000.0)
                led = AdvanceRepasseLedgerService(s)
                await led.credit(institution_id=inst.id, amount=100_000.0, source_type=RepasseLedgerSource.OPERATION, occurred_at=TODAY)
                svc = AdvanceSettlementService(s)
                o = await svc.add_movements(
                    batch_item_id=items[0].id, today=TODAY,
                    movements=[{"funding_source": "SALDO_REPASSE", "amount": 100_000.0}],
                )
                self.assertEqual(await led.balance(inst.id), Decimal("0.00"))
                mv_id = o["movimentacoes"][0]["id"]
                o2 = await svc.reverse_movement(movement_id=mv_id, reason="teste", today=TODAY)
                self.assertEqual(o2["valor_liquidado"], 0.0)
                self.assertEqual(o2["situacao"], EM_ABERTO)
                # DEBIT do ledger estornado → saldo volta a 100k
                self.assertEqual(await led.balance(inst.id), Decimal("100000.00"))
            finally:
                await s.rollback()

    async def test_vencida_when_past_due(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.advance_settlement_service import AdvanceSettlementService, VENCIDA

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                _inst, _batch, items, _ = await self._make_obligations(s, gross=100_000.0, due_date=PAST)
                svc = AdvanceSettlementService(s)
                obs = await svc.list_obligations(today=TODAY)
                mine = [o for o in obs if o["batch_item_id"] == items[0].id][0]
                self.assertEqual(mine["situacao"], VENCIDA)
                self.assertGreater(mine["dias_em_atraso"], 0)
            finally:
                await s.rollback()

    async def test_nn_same_invoice_two_obligations(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.models.receivable import ReceivableInvoice
        from app.models.project import Project
        from app.services.advance_settlement_service import AdvanceSettlementService
        from app.services.receivable_advance_batch_service import ReceivableAdvanceBatchService

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                inst = await self._lepta(s)
                project = Project(name=f"NN {uuid4().hex[:8]}", is_active=True)
                s.add(project)
                await s.flush()
                inv = ReceivableInvoice(
                    nf_number=f"NN-{uuid4().hex[:6]}", project_id=project.id,
                    issue_date=date(2026, 5, 1), due_days=30, due_date=date(2026, 6, 1),
                    gross_amount=80_000.0, net_amount=80_000.0, received_amount=0.0, invoice_status="EMITIDA",
                )
                s.add(inv)
                await s.flush()
                svc = ReceivableAdvanceBatchService(s)
                for _ in range(2):
                    b = await svc.create_batch(
                        institution_id=inst.id, received_amount=80_000.0, discount_amount=0.0, fee_amount=0.0,
                        repasse_enabled=True, receive_date=date(2026, 6, 10), repayment_date=FUTURE,
                        observation=None, invoice_ids=[inv.id], created_by_id=None,
                    )
                    await svc.confirm_batch(batch_id=b.id)
                    await s.flush()
                sset = AdvanceSettlementService(s)
                obs = await sset.list_obligations(today=TODAY)
                mine = [o for o in obs if o["invoice_id"] == inv.id]
                self.assertEqual(len(mine), 2)  # duas participações = duas obrigações
                self.assertNotEqual(mine[0]["batch_item_id"], mine[1]["batch_item_id"])
            finally:
                await s.rollback()

    async def test_settlement_talks_only_to_ledger_port(self) -> None:
        """Prova de desacoplamento: um Ledger falso (só a interface) é injetável."""
        from app.database.session import AsyncSessionLocal, engine
        from app.services.advance_settlement_service import AdvanceSettlementService

        class FakeLedger:
            def __init__(self):
                self.debits = []
                self._balance = Decimal("30000.00")
            async def credit(self, **kw):
                return None
            async def debit(self, **kw):
                self.debits.append(kw)
                return None
            async def balance(self, institution_id):
                return self._balance
            async def reverse_source(self, **kw):
                return 0

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                _inst, _batch, items, _ = await self._make_obligations(s, gross=100_000.0)
                fake = FakeLedger()
                svc = AdvanceSettlementService(s, ledger=fake)
                await svc.add_movements(
                    batch_item_id=items[0].id, today=TODAY,
                    movements=[{"funding_source": "SALDO_REPASSE", "amount": 30_000.0}],
                )
                self.assertEqual(len(fake.debits), 1)  # o settlement chamou debit() na interface
                self.assertEqual(fake.debits[0]["amount"], Decimal("30000.00"))
            finally:
                await s.rollback()


if __name__ == "__main__":
    unittest.main()
