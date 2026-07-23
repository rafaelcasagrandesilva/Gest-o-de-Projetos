"""Geração automática de Contas a Pagar a partir dos cadastros (Custos Fixos / Endividamento).

Valida: geração respeitando ciclo de vida; endividamento só quando obrigatório;
idempotência (nunca duplica); rótulos (Tipo/credor/centro/origem).
"""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from uuid import uuid4


class PayableAutoGenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_company_finance_auto_generation(self) -> None:
        from sqlalchemy import select, text
        from sqlalchemy.exc import ProgrammingError

        from app.database.session import AsyncSessionLocal, engine
        from app.models.company_finance import CompanyFinancialItem
        from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
        from app.services.payable_snapshot_service import PayableSnapshotService

        await engine.dispose()

        async with AsyncSessionLocal() as session:
            try:
                await session.execute(text("SELECT origin FROM payable_snapshots LIMIT 1"))
            except ProgrammingError:
                self.skipTest("Coluna origin ausente (rode alembic upgrade head).")

            comp = date(2099, 5, 1)  # competência futura isolada (sem snapshots reais)
            tag = uuid4().hex[:6]

            # Ativo, dentro da vigência → gera.
            fixed_ok = CompanyFinancialItem(
                tipo="custo_fixo", nome=f"Aluguel {tag}", valor_referencia=3000.0,
                is_active=True, start_date=date(2099, 1, 1), end_date=None,
                cost_center="Administrativo", cost_center_system="ADMINISTRATIVO",
            )
            # Inativo → não gera.
            fixed_inactive = CompanyFinancialItem(
                tipo="custo_fixo", nome=f"Cancelado {tag}", valor_referencia=500.0,
                is_active=False, start_date=date(2099, 1, 1), end_date=date(2099, 3, 31),
                cost_center="Administrativo", cost_center_system="ADMINISTRATIVO",
            )
            # Encerrado antes da competência → não gera.
            fixed_ended = CompanyFinancialItem(
                tipo="custo_fixo", nome=f"Encerrado {tag}", valor_referencia=700.0,
                is_active=True, start_date=date(2099, 1, 1), end_date=date(2099, 4, 30),
                cost_center="Administrativo", cost_center_system="ADMINISTRATIVO",
            )
            # Endividamento obrigatório e ativo → gera.
            debt_required = CompanyFinancialItem(
                tipo="endividamento", nome=f"Financiamento {tag}", valor_referencia=10000.0,
                is_active=True, is_monthly_required=True, start_date=date(2099, 1, 1),
                cost_center="Financeiro", cost_center_system="FINANCEIRO",
            )
            # Endividamento NÃO obrigatório → não gera (só controle).
            debt_optional = CompanyFinancialItem(
                tipo="endividamento", nome=f"Dívida controle {tag}", valor_referencia=8000.0,
                is_active=True, is_monthly_required=False, start_date=date(2099, 1, 1),
                cost_center="Financeiro", cost_center_system="FINANCEIRO",
            )
            for it in (fixed_ok, fixed_inactive, fixed_ended, debt_required, debt_optional):
                session.add(it)
            await session.flush()

            svc = PayableSnapshotService(session)
            test_refs = [fixed_ok.id, fixed_inactive.id, fixed_ended.id, debt_required.id, debt_optional.id]

            async def rows_for_test_refs():
                return list(
                    (
                        await session.execute(
                            select(PayableSnapshot).where(
                                PayableSnapshot.month == comp,
                                PayableSnapshot.ref_id.in_(test_refs),
                            )
                        )
                    ).scalars().all()
                )

            # A geração processa TODOS os itens ativos do banco; isolamos as asserções aos
            # itens do teste (o mês 2099-05 é limpo por completo no final).
            await svc._generate_company_finance_payables(payment_month=comp)
            await session.flush()

            by_ref = {r.ref_id: r for r in await rows_for_test_refs()}
            # Só o custo fixo ativo-em-vigência e o endividamento obrigatório geram linha.
            self.assertEqual(set(by_ref), {fixed_ok.id, debt_required.id})

            fx = by_ref[fixed_ok.id]
            self.assertEqual(fx.type, PayableSnapshotType.FIXED_COST)
            self.assertEqual(fx.category, "Custo Fixo")   # Tipo exibido
            self.assertEqual(fx.origin, "FIXED_COST")      # origem rastreável
            self.assertEqual(fx.name, f"Aluguel {tag}")    # credor = nome cadastrado
            self.assertEqual(float(fx.amount_final), 3000.0)  # valor de referência

            dbt = by_ref[debt_required.id]
            self.assertEqual(dbt.type, PayableSnapshotType.ENDIVIDAMENTO)
            self.assertEqual(dbt.origin, "DEBT")

            # Idempotência: rodar de novo NÃO cria duplicatas (todos os ativos já têm linha).
            created_again = await svc._generate_company_finance_payables(payment_month=comp)
            await session.flush()
            self.assertEqual(created_again, 0)
            by_ref_again = {r.ref_id: r for r in await rows_for_test_refs()}
            self.assertEqual(set(by_ref_again), {fixed_ok.id, debt_required.id})

            # Limpeza: remove TODAS as linhas do mês de teste (2099-05) e os itens criados.
            await session.execute(
                text("DELETE FROM payable_snapshots WHERE month = :m"), {"m": comp}
            )
            for it in (fixed_ok, fixed_inactive, fixed_ended, debt_required, debt_optional):
                fresh = await session.get(CompanyFinancialItem, it.id)
                if fresh is not None:
                    await session.delete(fresh)
            await session.commit()


class GenerationHonorsGridTests(unittest.IsolatedAsyncioTestCase):
    async def _prelude(self, session):
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        try:
            await session.execute(text("SELECT origin FROM payable_snapshots LIMIT 1"))
        except ProgrammingError:
            self.skipTest("Coluna origin ausente (rode alembic upgrade head).")

    async def test_grid_value_overrides_reference_at_generation(self) -> None:
        """>= piso: a geração usa o valor da grade quando informado (não o de referência)."""
        from sqlalchemy import select, text
        from app.database.session import AsyncSessionLocal, engine
        from app.models.company_finance import CompanyFinancialItem, CompanyFinancialPayment
        from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
        from app.services.payable_snapshot_service import PayableSnapshotService

        await engine.dispose()
        tag = uuid4().hex[:6]
        comp = date(2099, 6, 1)  # >= piso, mês futuro isolado

        async with AsyncSessionLocal() as session:
            await self._prelude(session)
            try:
                item = CompanyFinancialItem(
                    tipo="custo_fixo", nome=f"Aluguel {tag}", valor_referencia=400.0,
                    is_active=True, start_date=date(2099, 1, 1), end_date=None,
                    cost_center="Administrativo", cost_center_system="ADMINISTRATIVO",
                )
                session.add(item)
                await session.flush()
                # Valor oficial da competência informado na grade (500 != 400 de referência).
                session.add(CompanyFinancialPayment(item_id=item.id, competencia=comp, valor=Decimal("500.00")))
                await session.flush()

                await PayableSnapshotService(session)._generate_company_finance_payables(payment_month=comp)
                await session.flush()

                row = (
                    await session.execute(
                        select(PayableSnapshot).where(
                            PayableSnapshot.ref_id == item.id,
                            PayableSnapshot.month == comp,
                            PayableSnapshot.type == PayableSnapshotType.FIXED_COST,
                        )
                    )
                ).scalars().first()
                self.assertIsNotNone(row)
                self.assertEqual(float(row.amount_final), 500.0)  # grade, não 400 de referência
            finally:
                await session.rollback()

    async def test_below_floor_generates_only_with_grid_value(self) -> None:
        """< piso: só gera para itens COM valor na grade (item sem grade não retroage)."""
        from sqlalchemy import select
        from app.database.session import AsyncSessionLocal, engine
        from app.models.company_finance import CompanyFinancialItem, CompanyFinancialPayment
        from app.models.payable_snapshot import PayableSnapshot
        from app.services.payable_snapshot_service import PayableSnapshotService

        await engine.dispose()
        tag = uuid4().hex[:6]
        past = date(2026, 6, 1)  # < piso

        async with AsyncSessionLocal() as session:
            await self._prelude(session)
            try:
                with_grid = CompanyFinancialItem(
                    tipo="custo_fixo", nome=f"ComGrade {tag}", valor_referencia=400.0,
                    is_active=True, start_date=date(2019, 1, 1), end_date=None,
                    cost_center="Administrativo", cost_center_system="ADMINISTRATIVO",
                )
                without_grid = CompanyFinancialItem(
                    tipo="custo_fixo", nome=f"SemGrade {tag}", valor_referencia=400.0,
                    is_active=True, start_date=date(2019, 1, 1), end_date=None,
                    cost_center="Administrativo", cost_center_system="ADMINISTRATIVO",
                )
                session.add_all([with_grid, without_grid])
                await session.flush()
                session.add(CompanyFinancialPayment(item_id=with_grid.id, competencia=past, valor=Decimal("300.00")))
                await session.flush()

                await PayableSnapshotService(session)._generate_company_finance_payables(payment_month=past)
                await session.flush()

                async def row_for(ref):
                    return (
                        await session.execute(
                            select(PayableSnapshot).where(
                                PayableSnapshot.ref_id == ref, PayableSnapshot.month == past
                            )
                        )
                    ).scalars().first()

                with_row = await row_for(with_grid.id)
                self.assertIsNotNone(with_row)                 # gerou (tem grade)
                self.assertEqual(float(with_row.amount_final), 300.0)
                self.assertIsNone(await row_for(without_grid.id))  # não gerou (sem grade)
            finally:
                await session.rollback()


if __name__ == "__main__":
    unittest.main()
