"""Geração automática de Contas a Pagar a partir dos cadastros (Custos Fixos / Endividamento).

Valida: geração respeitando ciclo de vida; endividamento só quando obrigatório;
idempotência (nunca duplica); rótulos (Tipo/credor/centro/origem).
"""

from __future__ import annotations

import unittest
from datetime import date
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


if __name__ == "__main__":
    unittest.main()
