"""Ciclo de vida dos cadastros mestres (is_active + start_date + end_date).

Cobre a regra central: inativo exige data de encerramento; inativo não gera novos
lançamentos automáticos; exclusão física bloqueada quando há movimentação.
"""

from __future__ import annotations

import unittest
from datetime import date
from uuid import uuid4

from fastapi import HTTPException

from app.utils.lifecycle import (
    DELETE_WITH_MOVEMENT_MSG,
    INACTIVE_REQUIRES_END_DATE_MSG,
    normalize_lifecycle,
)


class NormalizeLifecycleTests(unittest.TestCase):
    def test_active_clears_end_date(self) -> None:
        # Ativo nunca possui encerramento (reativar reabre o ciclo).
        self.assertIsNone(normalize_lifecycle(is_active=True, end_date=date(2026, 1, 1)))
        self.assertIsNone(normalize_lifecycle(is_active=True, end_date=None))

    def test_inactive_requires_end_date(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            normalize_lifecycle(is_active=False, end_date=None)
        self.assertEqual(str(ctx.exception), INACTIVE_REQUIRES_END_DATE_MSG)

    def test_inactive_keeps_end_date(self) -> None:
        d = date(2026, 8, 31)
        self.assertEqual(normalize_lifecycle(is_active=False, end_date=d), d)


class CompanyFinanceLifecycleDBTests(unittest.IsolatedAsyncioTestCase):
    async def test_company_finance_item_lifecycle(self) -> None:
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        from app.database.session import AsyncSessionLocal, engine
        from app.models.company_finance import CompanyFinancialItem, CompanyFinancialPayment
        from app.services.company_finance_service import CompanyFinanceService

        await engine.dispose()

        async with AsyncSessionLocal() as session:
            try:
                await session.execute(
                    text("SELECT is_active FROM company_financial_items LIMIT 1")
                )
            except ProgrammingError:
                self.skipTest("Coluna is_active ausente (rode alembic upgrade head).")

            svc = CompanyFinanceService(session)

            # 1) Criação exige start_date (schema) e nasce ATIVO.
            item = await svc.create_item(
                actor_user_id=uuid4(),
                data={
                    "tipo": "custo_fixo",
                    "nome": f"CicloVida {uuid4().hex[:6]}",
                    "valor_referencia": 1000.0,
                    "cost_center_ref": "ADMINISTRATIVO",
                    "item_type": "MANUAL",
                    "is_active": True,
                    "start_date": date(2026, 1, 1),
                    "end_date": None,
                },
            )
            await session.flush()
            self.assertTrue(item.is_active)
            self.assertEqual(item.start_date, date(2026, 1, 1))

            # 2) Inativar SEM data de encerramento é rejeitado.
            with self.assertRaises(ValueError) as ctx:
                await svc.update_item(item_id=item.id, data={"is_active": False})
            self.assertEqual(str(ctx.exception), INACTIVE_REQUIRES_END_DATE_MSG)

            # 3) Inativar COM data de encerramento funciona.
            await svc.update_item(
                item_id=item.id, data={"is_active": False, "end_date": date(2026, 6, 30)}
            )
            await session.refresh(item)
            self.assertFalse(item.is_active)
            self.assertEqual(item.end_date, date(2026, 6, 30))

            # 4) Inativo bloqueia NOVO lançamento (competência sem pagamento anterior).
            with self.assertRaises(ValueError):
                await svc.replace_payments(
                    item_id=item.id, pagamentos=[{"mes": "2099-01", "valor": 500.0}]
                )

            # 5) Exclusão física bloqueada quando há movimentação (pagamento vinculado).
            session.add(
                CompanyFinancialPayment(item_id=item.id, competencia=date(2026, 1, 1), valor=1000.0)
            )
            await session.flush()
            with self.assertRaises(ValueError) as ctx:
                await svc.delete_item(item_id=item.id)
            self.assertEqual(str(ctx.exception), DELETE_WITH_MOVEMENT_MSG)

            # 6) Reativar limpa a data de encerramento.
            await svc.update_item(item_id=item.id, data={"is_active": True})
            await session.refresh(item)
            self.assertTrue(item.is_active)
            self.assertIsNone(item.end_date)

            # Limpeza (remoção direta, sem efeitos em contas a pagar).
            await session.execute(
                text("DELETE FROM company_financial_payments WHERE item_id = :i"), {"i": str(item.id)}
            )
            fresh = await session.get(CompanyFinancialItem, item.id)
            if fresh is not None:
                await session.delete(fresh)
            await session.commit()


class EmployeeMovementDBTests(unittest.IsolatedAsyncioTestCase):
    async def test_delete_blocked_with_movement(self) -> None:
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        from app.database.session import AsyncSessionLocal, engine
        from app.models.company_finance import CompanyFinancialItem
        from app.models.employee import Employee
        from app.services.employees_service import EmployeesService

        await engine.dispose()

        async with AsyncSessionLocal() as session:
            try:
                await session.execute(text("SELECT start_date FROM employees LIMIT 1"))
            except ProgrammingError:
                self.skipTest("Coluna start_date ausente (rode alembic upgrade head).")

            emp = Employee(
                full_name=f"Ciclo {uuid4().hex[:6]}",
                employment_type="PJ",
                is_active=True,
                start_date=date(2026, 1, 1),
                total_cost=0,
            )
            session.add(emp)
            await session.flush()

            svc = EmployeesService(session)
            # Sem movimentação → pode excluir (não chamamos delete p/ evitar commit; usamos helper).
            self.assertFalse(await svc._has_movement(emp.id))

            # Cria vínculo (item de custo-matriz) → passa a ter movimentação.
            link = CompanyFinancialItem(
                tipo="custo_fixo",
                nome=f"Matriz {uuid4().hex[:6]}",
                valor_referencia=100.0,
                employee_id=emp.id,
                is_active=True,
            )
            session.add(link)
            await session.flush()
            self.assertTrue(await svc._has_movement(emp.id))

            # delete_employee deve recusar com a mensagem padrão.
            with self.assertRaises(HTTPException) as ctx:
                await svc.delete_employee(actor_user_id=uuid4(), employee_id=emp.id)
            self.assertEqual(ctx.exception.detail, DELETE_WITH_MOVEMENT_MSG)

            # Limpeza.
            await session.delete(link)
            await session.delete(emp)
            await session.commit()


if __name__ == "__main__":
    unittest.main()
