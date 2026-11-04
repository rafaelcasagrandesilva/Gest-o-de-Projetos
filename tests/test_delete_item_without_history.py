"""Exclusão de cadastro (Custos Fixos/Endividamento): só histórico REAL bloqueia.

Criar o item já gera, sozinho, os lançamentos da grade e os títulos ABERTOS do Contas a Pagar.
Antes, esses lançamentos contavam como "movimentação" e o item criado por engano não podia ser
excluído pela tela. Agora bloqueiam só: título pago, pagamento ativo (estornado não conta) e
lançamento da grade sem título (histórico digitado à mão).

Tudo roda numa transação desfeita no fim — nada fica no banco.
"""

from __future__ import annotations

import unittest
from datetime import date
from uuid import uuid4

from sqlalchemy import func, select


def _debt(nome: str) -> dict:
    return {
        "tipo": "endividamento",
        "nome": nome,
        "valor_referencia": 25000.0,
        "cost_center_ref": "ADMINISTRATIVO",
        "item_type": "MANUAL",
        "is_active": True,
        # "Obrigatório mensal": é o que faz a criação materializar grade + títulos abertos.
        "is_monthly_required": True,
        "start_date": date(2026, 4, 10),
        "end_date": None,
    }


class DeleteItemWithoutHistoryDBTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        from sqlalchemy import text
        from sqlalchemy.exc import OperationalError, ProgrammingError

        from app.database.session import AsyncSessionLocal, engine

        await engine.dispose()
        self.session = AsyncSessionLocal()
        try:
            await self.session.execute(text("SELECT entry_id FROM payable_snapshots LIMIT 1"))
        except (ProgrammingError, OperationalError, OSError):
            await self.session.close()
            self.skipTest("Banco de testes indisponível ou sem migrations.")

    async def asyncTearDown(self) -> None:
        from app.database.session import engine

        await self.session.rollback()
        await self.session.close()
        # Cada teste roda num event loop próprio: conexão que sobra no pool quebra o próximo.
        await engine.dispose()

    async def _counts(self, item_id) -> tuple[int, int, int]:
        from app.models.company_finance import CompanyFinancialItem, CompanyFinancialPayment
        from app.models.payable_snapshot import PayableSnapshot

        s = self.session
        items = (await s.execute(select(func.count()).select_from(CompanyFinancialItem).where(CompanyFinancialItem.id == item_id))).scalar_one()
        titulos = (await s.execute(select(func.count()).select_from(PayableSnapshot).where(PayableSnapshot.ref_id == item_id))).scalar_one()
        grade = (await s.execute(select(func.count()).select_from(CompanyFinancialPayment).where(CompanyFinancialPayment.item_id == item_id))).scalar_one()
        return items, titulos, grade

    async def test_created_by_mistake_can_be_deleted(self) -> None:
        from app.services.company_finance_service import CompanyFinanceService

        svc = CompanyFinanceService(self.session)
        item = await svc.create_item(actor_user_id=uuid4(), data=_debt(f"Engano {uuid4().hex[:6]}"))
        await self.session.flush()
        _, titulos, grade = await self._counts(item.id)
        self.assertGreater(titulos, 0, "a criação deveria ter gerado títulos abertos")
        self.assertGreater(grade, 0, "a criação deveria ter gerado lançamentos na grade")

        self.assertTrue(await svc.delete_item(item_id=item.id))
        await self.session.flush()
        self.assertEqual(await self._counts(item.id), (0, 0, 0))

    async def test_paid_title_blocks_delete(self) -> None:
        from app.models.payable_snapshot import PayableSnapshot
        from app.services.company_finance_service import DELETE_WITH_MOVEMENT_MSG, CompanyFinanceService

        svc = CompanyFinanceService(self.session)
        item = await svc.create_item(actor_user_id=uuid4(), data=_debt(f"Pago {uuid4().hex[:6]}"))
        await self.session.flush()
        titulo = (await self.session.execute(select(PayableSnapshot).where(PayableSnapshot.ref_id == item.id).limit(1))).scalar_one()
        titulo.amount_paid = 100
        await self.session.flush()

        with self.assertRaises(ValueError) as ctx:
            await svc.delete_item(item_id=item.id)
        self.assertEqual(str(ctx.exception), DELETE_WITH_MOVEMENT_MSG)

    async def _item_with_registered_payment(self, tag: str):
        from app.models.payable_snapshot import PayableSnapshot
        from app.services.company_finance_service import CompanyFinanceService
        from app.services.payable_snapshot_service import PayableSnapshotService

        svc = CompanyFinanceService(self.session)
        item = await svc.create_item(actor_user_id=uuid4(), data=_debt(f"{tag} {uuid4().hex[:6]}"))
        await self.session.flush()
        titulo = (
            await self.session.execute(select(PayableSnapshot).where(PayableSnapshot.ref_id == item.id).limit(1))
        ).scalar_one()
        await PayableSnapshotService(self.session).register_payment(
            row=titulo, amount=100.0, payment_date=date(2026, 7, 10)
        )
        await self.session.flush()
        return svc, item, titulo

    async def test_active_payment_blocks_delete(self) -> None:
        from app.services.company_finance_service import DELETE_WITH_MOVEMENT_MSG

        svc, item, _ = await self._item_with_registered_payment("Ativo")
        with self.assertRaises(ValueError) as ctx:
            await svc.delete_item(item_id=item.id)
        self.assertEqual(str(ctx.exception), DELETE_WITH_MOVEMENT_MSG)

    async def test_reversed_payment_does_not_block_delete(self) -> None:
        """Lançado no item errado: estornar → excluir → registrar no certo (fluxo pela tela)."""
        from app.services.payable_snapshot_service import PayableSnapshotService

        svc, item, titulo = await self._item_with_registered_payment("Estorno")
        await PayableSnapshotService(self.session).reverse_payment(
            row=titulo, amount=100.0, reversal_reason="lançado no item errado"
        )
        await self.session.flush()

        self.assertTrue(await svc.delete_item(item_id=item.id))
        await self.session.flush()
        self.assertEqual(await self._counts(item.id), (0, 0, 0))

    async def test_manual_entry_without_title_blocks_delete(self) -> None:
        from app.models.company_finance import CompanyFinancialPayment
        from app.services.company_finance_service import DELETE_WITH_MOVEMENT_MSG, CompanyFinanceService

        svc = CompanyFinanceService(self.session)
        item = await svc.create_item(actor_user_id=uuid4(), data=_debt(f"Manual {uuid4().hex[:6]}"))
        await self.session.flush()
        # Histórico digitado à mão antes do CAP: lançamento sem título vinculado.
        self.session.add(CompanyFinancialPayment(item_id=item.id, competencia=date(2026, 5, 1), valor=1000.0))
        await self.session.flush()

        with self.assertRaises(ValueError) as ctx:
            await svc.delete_item(item_id=item.id)
        self.assertEqual(str(ctx.exception), DELETE_WITH_MOVEMENT_MSG)


if __name__ == "__main__":
    unittest.main()
