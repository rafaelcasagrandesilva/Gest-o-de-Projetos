"""Fase 3 — indicadores gerenciais + timeline + históricos (backend, capability-driven).

Testes de banco NÃO commitam (rollback ao final). Instituição LEPTA NOVA por teste → saldo isolado.
"""

from __future__ import annotations

import unittest
from datetime import date
from uuid import uuid4

TODAY = date(2026, 8, 6)
FUTURE = date(2026, 12, 1)
SOON = date(2026, 8, 20)  # dentro de 30 dias de TODAY


class _Base(unittest.IsolatedAsyncioTestCase):
    async def _prelude(self, s):
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        try:
            await s.execute(text("SELECT 1 FROM advance_settlement_movements LIMIT 1"))
        except ProgrammingError:
            self.skipTest("Tabelas da Fase 1A ausentes (rode alembic upgrade head).")

    async def _lepta(self, s):
        from app.models.advance_institution import AdvanceInstitution

        inst = AdvanceInstitution(
            name=f"LEPTA Teste {uuid4().hex[:10]}", institution_type="FACTORING",
            operation_profile="LEPTA", is_active=True,
        )
        s.add(inst)
        await s.flush()
        return inst

    async def _confirm(self, s, *, inst, gross=100_000.0, repayment=FUTURE, repasse=True, daycoval=False):
        from app.models.project import Project
        from app.models.receivable import ReceivableInvoice
        from app.services.receivable_advance_batch_service import ReceivableAdvanceBatchService

        project = Project(name=f"F3 {uuid4().hex[:8]}", is_active=True)
        s.add(project)
        await s.flush()
        inv = ReceivableInvoice(
            nf_number=f"F3-{uuid4().hex[:6]}", project_id=project.id,
            issue_date=date(2026, 5, 1), due_days=30, due_date=date(2026, 6, 1),
            gross_amount=gross, net_amount=gross, received_amount=0.0, invoice_status="EMITIDA",
        )
        s.add(inv)
        await s.flush()
        svc = ReceivableAdvanceBatchService(s)
        # Daycoval exige valor antecipado manual por NF (items_config).
        items_config = [{"invoice_id": inv.id, "advanced_amount": gross}] if daycoval else None
        batch = await svc.create_batch(
            institution_id=inst.id, received_amount=gross, discount_amount=0.0,
            fee_amount=0.0, repasse_enabled=repasse, receive_date=date(2026, 6, 10),
            repayment_date=repayment, observation=None,
            invoice_ids=([] if daycoval else [inv.id]), items_config=items_config, created_by_id=None,
        )
        await svc.confirm_batch(batch_id=batch.id)
        await s.flush()
        loaded = await svc.get_batch(batch.id)
        return svc, batch, list(loaded.items)[0], inv


class ManagementTests(_Base):
    async def test_management_summary_distribution_and_avg(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.advance_settlement_service import AdvanceSettlementService

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                inst = await self._lepta(s)
                _svc, _batch, item, _inv = await self._confirm(s, inst=inst, gross=100_000.0)
                sset = AdvanceSettlementService(s)
                # Repasse (7000 creditado no confirm) → usa 3000; Caixa 2000.
                await sset.add_movements(
                    batch_item_id=item.id, today=TODAY,
                    movements=[
                        {"funding_source": "SALDO_REPASSE", "amount": 3_000.0, "settled_at": TODAY},
                        {"funding_source": "CAIXA_EMPRESA", "amount": 2_000.0, "settled_at": TODAY},
                    ],
                )
                ms = await sset.management_summary(today=TODAY, institution_id=inst.id)
                self.assertEqual(ms["liquidado_repasse"], 3_000.0)
                self.assertEqual(ms["liquidado_outras_origens"], 2_000.0)
                self.assertEqual(ms["total_liquidado"], 5_000.0)
                self.assertEqual(ms["valor_ainda_antecipado"], 95_000.0)  # residual
                # Tempo médio: receive 2026-06-10 → TODAY 2026-08-06 = 57 dias.
                self.assertEqual(ms["tempo_medio_liquidacao_dias"], 57.0)
                dist = {d["funding_source"]: d for d in ms["distribuicao_origens"]}
                self.assertEqual(dist["SALDO_REPASSE"]["total"], 3_000.0)
                self.assertEqual(dist["SALDO_REPASSE"]["pct"], 60.0)
                self.assertEqual(dist["CAIXA_EMPRESA"]["pct"], 40.0)
            finally:
                await s.rollback()

    async def test_a_vencer_30d_and_vencido(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.advance_settlement_service import AdvanceSettlementService

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                inst = await self._lepta(s)
                # Uma a vencer em 20/08 (dentro de 30d) e uma já vencida (venc. no passado).
                await self._confirm(s, inst=inst, gross=100_000.0, repayment=SOON)
                await self._confirm(s, inst=inst, gross=50_000.0, repayment=date(2026, 7, 1))
                sset = AdvanceSettlementService(s)
                ms = await sset.management_summary(today=TODAY, institution_id=inst.id)
                self.assertEqual(ms["valor_a_vencer_30d"], 100_000.0)
                self.assertEqual(ms["valor_vencido"], 50_000.0)
                self.assertEqual(ms["valor_ainda_antecipado"], 150_000.0)
            finally:
                await s.rollback()

    async def test_timeline_events_sequence(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.advance_settlement_service import AdvanceSettlementService

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                inst = await self._lepta(s)
                _svc, _batch, item, _inv = await self._confirm(s, inst=inst, gross=100_000.0, repayment=date(2026, 7, 1))
                sset = AdvanceSettlementService(s)
                await sset.add_movements(
                    batch_item_id=item.id, today=TODAY,
                    movements=[{"funding_source": "CAIXA_EMPRESA", "amount": 40_000.0, "settled_at": date(2026, 7, 20)}],
                )
                await sset.add_movements(
                    batch_item_id=item.id, today=TODAY,
                    movements=[{"funding_source": "RECEBIMENTO_CLIENTE", "amount": 60_000.0, "settled_at": TODAY}],
                )
                tl = await sset.obligation_timeline(item.id, today=TODAY)
                labels = [e["label"] for e in tl["events"]]
                # Antecipada → Venceu → Liquidação parcial → Liquidada
                self.assertEqual(labels[0], "Antecipada")
                self.assertIn("Venceu", labels)
                self.assertIn("Liquidação parcial", labels)
                self.assertEqual(labels[-1], "Liquidada")
                self.assertEqual(tl["situacao"], "LIQUIDADA")
            finally:
                await s.rollback()

    async def test_capability_excludes_daycoval(self) -> None:
        from sqlalchemy import select
        from app.database.session import AsyncSessionLocal, engine
        from app.models.advance_institution import AdvanceInstitution
        from app.services.advance_settlement_service import AdvanceSettlementService

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                # Daycoval: perfil sem obrigação de liquidação → não aparece nos indicadores.
                day = (
                    await s.execute(select(AdvanceInstitution).where(AdvanceInstitution.operation_profile == "DAYCOVAL"))
                ).scalars().first()
                if day is None:
                    day = AdvanceInstitution(name=f"DAY {uuid4().hex[:8]}", institution_type="BANK",
                                             operation_profile="DAYCOVAL", is_active=True)
                    s.add(day)
                    await s.flush()
                # Cria operação Daycoval (liquida a NF como RECEBIDA; não gera obrigação).
                await self._confirm(s, inst=day, gross=80_000.0, repayment=FUTURE, repasse=False, daycoval=True)
                sset = AdvanceSettlementService(s)
                obs = [o for o in await sset.list_obligations(today=TODAY) if o["institution_id"] == day.id]
                self.assertEqual(len(obs), 0)  # capability creates_settlement_obligation=False
            finally:
                await s.rollback()

    async def test_invoice_history(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.advance_settlement_service import AdvanceSettlementService

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                inst = await self._lepta(s)
                _svc, _batch, _item, inv = await self._confirm(s, inst=inst, gross=100_000.0)
                sset = AdvanceSettlementService(s)
                hist = await sset.invoice_history(inv.id, today=TODAY)
                self.assertEqual(hist["invoice_id"], inv.id)
                self.assertEqual(len(hist["obrigacoes"]), 1)
                self.assertEqual(hist["obrigacoes"][0]["invoice_id"], inv.id)
            finally:
                await s.rollback()

    async def test_batch_history(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.advance_settlement_service import AdvanceSettlementService

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                inst = await self._lepta(s)
                _svc, batch, _item, _inv = await self._confirm(s, inst=inst, gross=100_000.0, repasse=True)
                sset = AdvanceSettlementService(s)
                hist = await sset.batch_history(batch.id, today=TODAY)
                self.assertEqual(hist["batch_id"], batch.id)
                self.assertEqual(len(hist["obrigacoes"]), 1)
                # Repasse (7% creditado no confirm) aparece como 1 lançamento de Entrada.
                self.assertEqual(len(hist["repasse"]), 1)
                self.assertEqual(hist["repasse"][0]["direction"], "CREDIT")
                self.assertEqual(hist["repasse"][0]["amount"], 7_000.0)
            finally:
                await s.rollback()


if __name__ == "__main__":
    unittest.main()
