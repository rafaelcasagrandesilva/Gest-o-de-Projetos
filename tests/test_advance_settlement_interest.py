"""Liquidação de NFs — prorrogação de vencimento (com custo) e juros.

- prorrogar muda o vencimento VIGENTE (situação/atraso), mantém o original e aceita desfazer só a
  última; a nova data tem de ser posterior à vigente; NF liquidada não prorroga;
- pedido de prorrogação (uma ou várias NFs da mesma instituição, custo único) gera o título no
  Contas a Pagar e soma no custo real das antecipações; desfazer leva o pedido inteiro e o título,
  e é bloqueado com o título pago;
- pagar acima do residual só é aceito em NF prorrogada ou paga após o vencimento original; o
  excedente vira juros (não abate a obrigação) e sai inteiro do Repasse; estornar devolve tudo;
- indicadores: percentual sobre o valor da obrigação e taxa mensal equivalente, contados do
  vencimento ORIGINAL até o pagamento.

Testes de banco NÃO commitam (rollback ao final).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from tests.test_advance_settlement_ledger import _Base

HOJE = date(2026, 9, 12)
VENCIMENTO = date(2026, 9, 10)


class ExtensionTests(_Base):
    async def test_prorrogar_e_desfazer(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.advance_settlement_service import (
            AdvanceSettlementService,
            EM_ABERTO,
            VENCIDA,
        )

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                _inst, _b, items, _ = await self._make_obligations(s, gross=83_468.22, due_date=VENCIMENTO)
                svc = AdvanceSettlementService(s)
                o = await svc.get_obligation(items[0].id, today=HOJE)
                self.assertEqual((o["situacao"], o["dias_em_atraso"], o["prorrogada"]), (VENCIDA, 2, False))

                with self.assertRaises(ValueError):  # não pode ser antes/igual ao vigente
                    await svc.extend_due_date(batch_item_id=items[0].id, new_due=VENCIMENTO, reason=None, today=HOJE)

                o = await svc.extend_due_date(
                    batch_item_id=items[0].id, new_due=date(2026, 9, 18), reason="Acordo com a Lepta", today=HOJE
                )
                self.assertEqual(o["vencimento"], date(2026, 9, 18))
                self.assertEqual(o["vencimento_original"], VENCIMENTO)
                self.assertEqual((o["situacao"], o["dias_em_atraso"], o["prorrogada"]), (EM_ABERTO, 0, True))

                o = await svc.extend_due_date(
                    batch_item_id=items[0].id, new_due=date(2026, 9, 25), reason=None, today=HOJE
                )
                primeira, segunda = o["prorrogacoes"]
                self.assertEqual(segunda["previous_due"], date(2026, 9, 18))
                with self.assertRaises(ValueError):  # só a mais recente
                    await svc.undo_extension(extension_id=primeira["id"], today=HOJE)
                o = await svc.undo_extension(extension_id=segunda["id"], today=HOJE)
                self.assertEqual(o["vencimento"], date(2026, 9, 18))
            finally:
                await s.rollback()


class ExtensionCostTests(_Base):
    async def test_prorrogacao_em_massa_gera_titulo_e_desfaz_junto(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
        from app.services.advance_settlement_service import AdvanceSettlementService
        from app.services.anticipation_rate import AnticipationRateResolver

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                inst, _b, items, invs = await self._make_obligations(s, gross=10_000.0, n=3, due_date=VENCIMENTO)
                svc = AdvanceSettlementService(s)
                antes = (await AnticipationRateResolver(s, lambda m: 0).monthly_costs()).get(date(2026, 9, 1), 0.0)

                rows = await svc.extend_due_dates(
                    batch_item_ids=[i.id for i in items], new_due=date(2026, 9, 25),
                    cost_amount=1_234.56, cost_payment_date=date(2026, 9, 11),
                    observation="E-mail da Lepta", today=HOJE,
                )
                self.assertEqual({r["vencimento"] for r in rows}, {date(2026, 9, 25)})
                p = rows[0]["prorrogacoes"][-1]
                self.assertEqual((p["custo"], p["nfs_no_pedido"], p["custo_pago"]), (1_234.56, 3, False))
                # Taxa do pedido: 1.234,56 sobre 30.000 (3 NFs) em 15 dias (10/09 → 25/09).
                self.assertEqual((p["taxa_base"], p["taxa_dias"]), (30_000.0, 15.0))
                self.assertAlmostEqual(p["taxa_periodo"], 1_234.56 / 30_000, places=6)
                self.assertAlmostEqual(p["taxa_mensal"], (1 + 1_234.56 / 30_000) ** 2 - 1, places=6)
                # Estimativa por NF: mesmos valor e dias → partes iguais, somando o custo exato.
                partes = [r["prorrogacoes"][-1]["custo_nf"] for r in rows]
                self.assertAlmostEqual(sum(partes), 1_234.56, places=2)
                self.assertTrue(all(r["prorrogacoes"][-1]["custo_nf_estimado"] for r in rows))
                self.assertEqual(rows[0]["prorrogacoes"][-1]["taxa_nf_dias"], 15)

                from sqlalchemy import select
                titulo = (
                    await s.execute(select(PayableSnapshot).where(PayableSnapshot.ref_id == p["request_id"]))
                ).scalar_one()
                self.assertEqual(titulo.type, PayableSnapshotType.ANTECIPACAO_OPERACAO)
                self.assertEqual((float(titulo.amount_final), titulo.due_date), (1_234.56, date(2026, 9, 11)))
                self.assertEqual((titulo.cost_center, titulo.category), ("Financeiro", "Custo de prorrogação"))
                self.assertIn(inst.name, titulo.name)
                for inv in invs:
                    self.assertIn(inv.nf_number, titulo.name)

                # Custo entra no custo real das antecipações do mês do pagamento.
                depois = (await AnticipationRateResolver(s, lambda m: 0).monthly_costs()).get(date(2026, 9, 1), 0.0)
                self.assertAlmostEqual(depois - antes, 1_234.56, places=2)

                # Pago → não desfaz; em aberto → desfaz o pedido inteiro e apaga o título.
                titulo.paid = True
                await s.flush()
                with self.assertRaises(ValueError):
                    await svc.undo_extension(extension_id=p["id"], today=HOJE)
                titulo.paid = False
                await s.flush()
                o = await svc.undo_extension(extension_id=p["id"], today=HOJE)
                self.assertEqual((o["vencimento"], o["prorrogada"]), (VENCIMENTO, False))
                todas = {x["batch_item_id"]: x for x in await svc.list_obligations(today=HOJE)}
                self.assertTrue(all(not todas[i.id]["prorrogada"] for i in items))
                self.assertIsNone(await s.get(PayableSnapshot, titulo.id))
            finally:
                await s.rollback()

    async def test_massa_recusa_instituicoes_diferentes(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.advance_settlement_service import AdvanceSettlementService

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                _i1, _b1, a, _ = await self._make_obligations(s, gross=1_000.0, due_date=VENCIMENTO)
                _i2, _b2, b, _ = await self._make_obligations(s, gross=1_000.0, due_date=VENCIMENTO)
                with self.assertRaises(ValueError):
                    await AdvanceSettlementService(s).extend_due_dates(
                        batch_item_ids=[a[0].id, b[0].id], new_due=date(2026, 9, 25), today=HOJE
                    )
            finally:
                await s.rollback()


class InterestTests(_Base):
    async def test_juros_em_nf_prorrogada_saem_do_repasse(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.models.advance_repasse_ledger import RepasseLedgerSource
        from app.services.advance_repasse_ledger_service import AdvanceRepasseLedgerService
        from app.services.advance_settlement_service import AdvanceSettlementService, LIQUIDADA

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                inst, _b, items, _ = await self._make_obligations(s, gross=100_000.0, due_date=VENCIMENTO)
                led = AdvanceRepasseLedgerService(s)
                await led.credit(
                    institution_id=inst.id, amount=200_000.0, source_type=RepasseLedgerSource.OPERATION,
                    occurred_at=date(2026, 9, 1),
                )
                svc = AdvanceSettlementService(s)
                await svc.extend_due_date(
                    batch_item_id=items[0].id, new_due=date(2026, 9, 18), reason=None, today=date(2026, 9, 9)
                )
                # Parcial dentro do valor, depois o resto + juros, no dia 18 (8 dias após o original).
                await svc.add_movements(
                    batch_item_id=items[0].id, today=date(2026, 9, 9),
                    movements=[{"funding_source": "CAIXA_EMPRESA", "amount": 40_000.0,
                                "settled_at": date(2026, 9, 9)}],
                )
                o = await svc.add_movements(
                    batch_item_id=items[0].id, today=date(2026, 9, 18),
                    movements=[{"funding_source": "SALDO_REPASSE", "amount": 61_500.0,
                                "settled_at": date(2026, 9, 18)}],
                )
                self.assertEqual(o["situacao"], LIQUIDADA)
                self.assertEqual(o["valor_liquidado"], 100_000.0)
                self.assertEqual(o["juros_pagos"], 1_500.0)
                self.assertEqual(o["juros_percentual"], 0.015)
                self.assertEqual(o["juros_dias"], 8)
                self.assertAlmostEqual(o["juros_mensal"], (1.015 ** (30 / 8)) - 1, places=4)
                ultima = o["movimentacoes"][-1]
                self.assertEqual((ultima["amount"], ultima["interest_amount"]), (60_000.0, 1_500.0))
                # O Repasse pagou tudo o que saiu (principal + juros).
                self.assertEqual(await led.balance(inst.id), Decimal("138500.00"))

                o = await svc.reverse_movement(movement_id=ultima["id"], today=date(2026, 9, 18))
                self.assertEqual((o["valor_liquidado"], o["juros_pagos"]), (40_000.0, 0.0))
                self.assertEqual(await led.balance(inst.id), Decimal("200000.00"))
            finally:
                await s.rollback()

    async def test_juros_em_atraso_sem_prorrogacao_e_bloqueio_em_dia(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.advance_settlement_service import AdvanceSettlementService

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            await self._prelude(s)
            try:
                _i, _b, items, _ = await self._make_obligations(s, gross=10_000.0, n=2, due_date=VENCIMENTO)
                svc = AdvanceSettlementService(s)
                # Paga em dia (antes do vencimento) acima do valor: bloqueado.
                with self.assertRaises(ValueError):
                    await svc.add_movements(
                        batch_item_id=items[0].id, today=date(2026, 9, 5),
                        movements=[{"funding_source": "CAIXA_EMPRESA", "amount": 10_100.0,
                                    "settled_at": date(2026, 9, 5)}],
                    )
                # Paga em atraso, sem prorrogação: aceito, o excedente é juros.
                o = await svc.add_movements(
                    batch_item_id=items[1].id, today=date(2026, 9, 20),
                    movements=[{"funding_source": "CAIXA_EMPRESA", "amount": 10_100.0,
                                "settled_at": date(2026, 9, 20)}],
                )
                self.assertEqual((o["valor_liquidado"], o["juros_pagos"], o["juros_dias"]), (10_000.0, 100.0, 10))
            finally:
                await s.rollback()
