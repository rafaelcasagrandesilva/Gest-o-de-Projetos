"""Geração automática de Custos Fixos/Endividamento não retroage (piso JUL/2026) + limpeza
segura dos resíduos criados indevidamente em competências anteriores.

Os testes de banco NÃO commitam (rollback ao final) — não alteram dados reais do banco.
"""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from uuid import uuid4


class PreLaunchConstantTests(unittest.TestCase):
    def test_first_competence_is_july_2026(self) -> None:
        from app.services.payable_snapshot_service import COMPANY_FINANCE_AUTOGEN_FIRST_COMPETENCE

        self.assertEqual(COMPANY_FINANCE_AUTOGEN_FIRST_COMPETENCE, date(2026, 7, 1))


class PreLaunchGuardDBTests(unittest.IsolatedAsyncioTestCase):
    async def test_guard_blocks_before_july_2026(self) -> None:
        from sqlalchemy import select, text
        from sqlalchemy.exc import ProgrammingError

        from app.database.session import AsyncSessionLocal, engine
        from app.models.company_finance import CompanyFinancialItem
        from app.models.payable_snapshot import PayableSnapshot
        from app.services.payable_snapshot_service import PayableSnapshotService

        await engine.dispose()
        tag = uuid4().hex[:6]

        async with AsyncSessionLocal() as session:
            try:
                await session.execute(text("SELECT origin FROM payable_snapshots LIMIT 1"))
            except ProgrammingError:
                self.skipTest("Coluna origin ausente (rode alembic upgrade head).")
            try:
                item = CompanyFinancialItem(
                    tipo="custo_fixo",
                    nome=f"Aluguel piso {tag}",
                    valor_referencia=3000.0,
                    is_active=True,
                    start_date=date(2019, 1, 1),
                    end_date=None,
                    cost_center="Administrativo",
                    cost_center_system="ADMINISTRATIVO",
                )
                session.add(item)
                await session.flush()

                svc = PayableSnapshotService(session)

                async def has_row(month: date) -> bool:
                    r = await session.execute(
                        select(PayableSnapshot).where(
                            PayableSnapshot.month == month,
                            PayableSnapshot.ref_id == item.id,
                        )
                    )
                    return r.scalar_one_or_none() is not None

                # Competência anterior ao piso, item SEM valor na grade → NÃO gera.
                # (O piso só bloqueia geração baseada no valor de REFERÊNCIA; itens com valor
                #  explícito na grade podem gerar mesmo abaixo do piso — testado à parte.)
                await svc._generate_company_finance_payables(payment_month=date(2026, 6, 1))
                await session.flush()
                self.assertFalse(await has_row(date(2026, 6, 1)))

                # Competência muito anterior → idem (sem grade, não retroage).
                await svc._generate_company_finance_payables(payment_month=date(2020, 1, 1))
                await session.flush()
                self.assertFalse(await has_row(date(2020, 1, 1)))

                # Competência >= piso → gera normalmente (mês futuro isolado).
                await svc._generate_company_finance_payables(payment_month=date(2099, 5, 1))
                await session.flush()
                self.assertTrue(await has_row(date(2099, 5, 1)))
            finally:
                await session.rollback()  # nunca persiste dados de teste


class PreLaunchPurgeDBTests(unittest.IsolatedAsyncioTestCase):
    async def test_purge_removes_only_safe_rows(self) -> None:
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        from app.database.session import AsyncSessionLocal, engine
        from app.models.payable_payment import PayablePayment
        from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
        from app.services.payable_snapshot_service import PayableSnapshotService

        await engine.dispose()
        tag = uuid4().hex[:6]
        past = date(2020, 3, 1)  # < JUL/2026, isolado
        after = date(2026, 7, 1)  # piso: NÃO deve ser removido

        def snap(*, origin, month, paid=Decimal("0"), snap_type=PayableSnapshotType.FIXED_COST):
            return PayableSnapshot(
                month=month,
                type=snap_type,
                ref_id=uuid4(),
                name=f"{origin}-{month:%Y%m}-{tag}",
                cost_center="Administrativo",
                category="Custo Fixo",
                origin=origin,
                amount_original=Decimal("100.00"),
                amount_final=Decimal("100.00"),
                amount_paid=paid,
                due_date=month,
                paid=paid > 0,
            )

        async with AsyncSessionLocal() as session:
            try:
                await session.execute(text("SELECT origin FROM payable_snapshots LIMIT 1"))
            except ProgrammingError:
                self.skipTest("Coluna origin ausente (rode alembic upgrade head).")
            try:
                # DEVE remover: auto FIXED_COST/DEBT, passado, sem pagamento.
                a = snap(origin="FIXED_COST", month=past)
                b = snap(origin="DEBT", month=past, snap_type=PayableSnapshotType.ENDIVIDAMENTO)
                # NÃO deve remover:
                c = snap(origin="FIXED_COST", month=past, paid=Decimal("100.00"))  # pago
                d = snap(origin="MANUAL", month=past, snap_type=PayableSnapshotType.MANUAL)  # manual
                e = snap(origin="PROJECT", month=past, snap_type=PayableSnapshotType.COLLABORATOR)  # projeto
                f = snap(origin="FIXED_COST", month=after)  # >= piso
                g = snap(origin="FIXED_COST", month=past)  # tem pagamento (estornado) registrado
                for r in (a, b, c, d, e, f, g):
                    session.add(r)
                await session.flush()

                # `g` recebe um pagamento estornado → "pagamento registrado" existe → preservar.
                session.add(
                    PayablePayment(
                        payable_snapshot_id=g.id,
                        amount=Decimal("50.00"),
                        payment_date=past,
                        reversed_at=date.today(),
                    )
                )
                await session.flush()

                svc = PayableSnapshotService(session)

                # Dry-run não remove nada.
                dry = await svc.purge_pre_launch_company_finance_payables(dry_run=True)
                self.assertEqual(dry["removed"], 0)
                self.assertGreaterEqual(dry["candidates"], 2)

                result = await svc.purge_pre_launch_company_finance_payables()
                self.assertGreaterEqual(result["removed"], 2)
                self.assertEqual(result["first_competence"], "2026-07")

                # Removidos: a, b.
                self.assertIsNone(await session.get(PayableSnapshot, a.id))
                self.assertIsNone(await session.get(PayableSnapshot, b.id))
                # Preservados: pago (c), manual (d), projeto (e), pós-piso (f), com pagamento (g).
                for r in (c, d, e, f, g):
                    self.assertIsNotNone(await session.get(PayableSnapshot, r.id), f"não devia remover {r.name}")
            finally:
                await session.rollback()  # nunca persiste alterações no banco real


if __name__ == "__main__":
    unittest.main()
