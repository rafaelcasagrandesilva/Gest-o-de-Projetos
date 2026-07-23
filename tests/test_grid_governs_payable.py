"""A grade mensal governa o valor da competência no Contas a Pagar.

Restaura a regra: o cadastro gera a 1ª linha (valor de referência); depois que a
competência existe, editar a caixa do mês atualiza o lançamento correspondente do CAP —
exceto quando já há pagamento (preserva histórico e avisa). Respeita o piso JUL/2026.

Testes de banco NÃO commitam (rollback ao final) — não alteram dados reais.
"""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from uuid import uuid4


def _fixed_item(tag: str):
    from app.models.company_finance import CompanyFinancialItem

    return CompanyFinancialItem(
        tipo="custo_fixo",
        nome=f"Aluguel grade {tag}",
        valor_referencia=4732.0,
        is_active=True,
        start_date=date(2019, 1, 1),
        end_date=None,
        cost_center="Administrativo",
        cost_center_system="ADMINISTRATIVO",
    )


class GridGovernsPayableTests(unittest.IsolatedAsyncioTestCase):
    async def _prelude(self, session):
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        try:
            await session.execute(text("SELECT origin FROM payable_snapshots LIMIT 1"))
        except ProgrammingError:
            self.skipTest("Coluna origin ausente (rode alembic upgrade head).")

    async def test_grid_edit_updates_cap_when_unpaid(self) -> None:
        from sqlalchemy import select
        from app.database.session import AsyncSessionLocal, engine
        from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
        from app.services.company_finance_service import CompanyFinanceService
        from app.services.payable_snapshot_service import PayableSnapshotService

        await engine.dispose()
        tag = uuid4().hex[:6]
        comp = date(2099, 5, 1)  # >= piso JUL/2026, mês futuro isolado

        async with AsyncSessionLocal() as session:
            await self._prelude(session)
            try:
                item = _fixed_item(tag)
                session.add(item)
                await session.flush()

                # 1ª linha do CAP gerada pelo cadastro (valor de referência).
                await PayableSnapshotService(session)._generate_company_finance_payables(payment_month=comp)
                await session.flush()

                async def cap_row():
                    return (
                        await session.execute(
                            select(PayableSnapshot).where(
                                PayableSnapshot.ref_id == item.id,
                                PayableSnapshot.month == comp,
                                PayableSnapshot.type == PayableSnapshotType.FIXED_COST,
                            )
                        )
                    ).scalars().first()

                row = await cap_row()
                self.assertIsNotNone(row)
                self.assertEqual(float(row.amount_final), 4732.0)  # referência

                # Usuário edita a grade do mês para R$ 100,00 → CAP passa a valer 100.
                cf = CompanyFinanceService(session)
                await cf.replace_payments(
                    item_id=item.id, pagamentos=[{"mes": "2099-05", "valor": 100.0}]
                )
                self.assertEqual(cf.last_payable_sync.get("skipped_paid"), [])

                row = await cap_row()
                self.assertEqual(float(row.amount_original), 100.0)
                self.assertEqual(float(row.amount_final), 100.0)  # governado pela grade
                self.assertEqual(float(row.amount_paid), 0.0)     # saldo = 100
            finally:
                await session.rollback()

    async def test_grid_edit_preserves_cap_when_paid(self) -> None:
        from sqlalchemy import select
        from app.database.session import AsyncSessionLocal, engine
        from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
        from app.services.company_finance_service import CompanyFinanceService
        from app.services.payable_snapshot_service import PayableSnapshotService

        await engine.dispose()
        tag = uuid4().hex[:6]
        comp = date(2099, 5, 1)

        async with AsyncSessionLocal() as session:
            await self._prelude(session)
            try:
                item = _fixed_item(tag)
                session.add(item)
                await session.flush()
                await PayableSnapshotService(session)._generate_company_finance_payables(payment_month=comp)
                await session.flush()

                row = (
                    await session.execute(
                        select(PayableSnapshot).where(
                            PayableSnapshot.ref_id == item.id, PayableSnapshot.month == comp
                        )
                    )
                ).scalars().first()
                # Simula pagamento registrado no lançamento.
                row.amount_paid = Decimal("50.00")
                await session.flush()

                cf = CompanyFinanceService(session)
                await cf.replace_payments(
                    item_id=item.id, pagamentos=[{"mes": "2099-05", "valor": 100.0}]
                )

                # Não sincroniza (preserva histórico) e reporta o mês para aviso.
                self.assertIn(comp, cf.last_payable_sync.get("skipped_paid"))
                await session.refresh(row)
                self.assertEqual(float(row.amount_final), 4732.0)  # inalterado
                self.assertEqual(float(row.amount_paid), 50.0)
            finally:
                await session.rollback()

    async def test_pre_july_open_competence_is_editable(self) -> None:
        """Competência ABERTA anterior ao piso (caso DEX/Junho): editar a grade atualiza o CAP.

        O piso só preserva o histórico — não pode impedir manutenção de competência aberta.
        Uma linha automática já existente numa competência < JUL/2026, sem pagamento, deve
        passar a valer o valor informado na grade.
        """
        from sqlalchemy import select
        from app.database.session import AsyncSessionLocal, engine
        from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType, PayableOrigin
        from app.services.payable_snapshot_service import PayableSnapshotService

        await engine.dispose()
        tag = uuid4().hex[:6]
        past = date(2026, 6, 1)  # < piso, porém competência ABERTA

        async with AsyncSessionLocal() as session:
            await self._prelude(session)
            try:
                item = _fixed_item(tag)
                session.add(item)
                await session.flush()

                # Linha automática já existente numa competência anterior ao piso (aberta).
                row = PayableSnapshot(
                    month=past,
                    type=PayableSnapshotType.FIXED_COST,
                    ref_id=item.id,
                    name=item.nome,
                    cost_center="Administrativo",
                    category="Custo Fixo",
                    origin=PayableOrigin.FIXED_COST.value,
                    amount_original=Decimal("4732.00"),
                    amount_final=Decimal("4732.00"),
                    amount_paid=Decimal("0"),
                    due_date=past,
                    paid=False,
                )
                session.add(row)
                # Usuário informa o valor real da competência na grade.
                from app.models.company_finance import CompanyFinancialPayment

                session.add(CompanyFinancialPayment(item_id=item.id, competencia=past, valor=Decimal("100.00")))
                await session.flush()

                res = await PayableSnapshotService(session).sync_company_finance_item_months(
                    item_id=item.id, months={past}
                )
                self.assertEqual(res["synced"], 1)  # competência aberta é editável
                self.assertEqual(res["skipped_paid"], [])
                await session.refresh(row)
                self.assertEqual(float(row.amount_final), 100.0)     # governado pela grade
                self.assertEqual(float(row.amount_original), 100.0)  # sem saldo/ajuste
            finally:
                await session.rollback()

    async def test_pre_july_grid_creates_missing_line_when_generated(self) -> None:
        """Caso DEX real: competência aberta anterior ao piso, mês já materializado, sem linha.

        Ao informar o valor na grade, o CAP passa a exibir a linha (criada pelo sync).
        """
        from sqlalchemy import select, text
        from app.database.session import AsyncSessionLocal, engine
        from app.models.company_finance import CompanyFinancialPayment
        from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
        from app.models.payable_snapshot_generation import PayableSnapshotGeneration
        from app.services.payable_snapshot_service import PayableSnapshotService

        await engine.dispose()
        tag = uuid4().hex[:6]
        past = date(2026, 6, 1)  # < piso

        async with AsyncSessionLocal() as session:
            await self._prelude(session)
            try:
                item = _fixed_item(tag)
                session.add(item)
                await session.flush()

                # Mês materializado (snapshot gerado) porém SEM linha do item (piso não gerou).
                if not await PayableSnapshotService(session).is_generated(month=past):
                    session.add(PayableSnapshotGeneration(month=past))
                await session.flush()

                # Usuário informa o valor da competência na grade.
                session.add(CompanyFinancialPayment(item_id=item.id, competencia=past, valor=Decimal("250.00")))
                await session.flush()

                res = await PayableSnapshotService(session).sync_company_finance_item_months(
                    item_id=item.id, months={past}
                )
                self.assertEqual(res["synced"], 1)

                row = (
                    await session.execute(
                        select(PayableSnapshot).where(
                            PayableSnapshot.ref_id == item.id,
                            PayableSnapshot.month == past,
                            PayableSnapshot.type == PayableSnapshotType.FIXED_COST,
                        )
                    )
                ).scalars().first()
                self.assertIsNotNone(row)  # linha criada pela manutenção da grade
                self.assertEqual(float(row.amount_final), 250.0)
            finally:
                await session.rollback()


if __name__ == "__main__":
    unittest.main()
