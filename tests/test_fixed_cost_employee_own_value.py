"""Custos Fixos — Colaborador com VALOR PRÓPRIO + natureza (ex.: Retirada de Capital).

Valida a conversão Manual → Colaborador (valor próprio) de um item com histórico pago:
- o título PAGO não tem valor/pagamento alterados, só nome/categoria;
- os títulos saem "<Colaborador> — <Natureza>" e ficam na categoria "Colaborador";
- o valor continua o da referência/grade (nunca custo do colaborador × percentual);
- Retirada de Capital fica fora da média mensal do colaborador;
- "Editar estrutura" de um item com colaborador não tira o título da categoria "Colaborador".
Testes de banco NÃO commitam (rollback ao final).
"""

from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError


class FixedCostEmployeeOwnValueTests(unittest.IsolatedAsyncioTestCase):
    async def _prelude(self, session, *comps: date) -> None:
        from app.models.payable_snapshot_generation import PayableSnapshotGeneration
        from app.services.payable_snapshot_service import PayableSnapshotService

        try:
            await session.execute(
                text("SELECT payment_component_type_id FROM company_financial_items LIMIT 1")
            )
        except ProgrammingError:
            self.skipTest("Coluna ausente (rode alembic upgrade head).")
        for comp in comps:
            if not await PayableSnapshotService(session).is_generated(month=comp):
                session.add(PayableSnapshotGeneration(month=comp, created_at=datetime.now(timezone.utc)))
        await session.flush()

    async def _nature(self, session):
        from app.models.payment_component import PaymentComponentType

        return (
            await session.execute(
                select(PaymentComponentType).where(PaymentComponentType.code == "retirada_capital")
            )
        ).scalar_one()

    async def _employee(self, session, tag: str):
        from app.models.employee import Employee

        # Custo do cadastro bem diferente do valor da retirada: se o valor viesse do
        # colaborador, o teste perceberia.
        emp = Employee(
            full_name=f"Socio {tag}", email=f"socio_{tag}@ex.com", employment_type="PJ",
            is_active=True, salary_base=1234.0, total_cost=1234.0,
        )
        session.add(emp)
        await session.flush()
        return emp

    async def _lines(self, session, item_id):
        from app.models.payable_snapshot import PayableSnapshot

        return list(
            (await session.execute(select(PayableSnapshot).where(PayableSnapshot.ref_id == item_id)))
            .scalars()
            .all()
        )

    async def test_manual_para_colaborador_preserva_pago_e_renomeia(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.models.company_finance import CompanyFinancialItem, CompanyFinancialItemType
        from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
        from app.services.company_finance_service import CompanyFinanceService
        from app.services.employees_service import EmployeesService

        await engine.dispose()
        paid_comp, open_comp = date(2099, 1, 1), date(2099, 2, 1)
        async with AsyncSessionLocal() as s:
            await self._prelude(s, paid_comp, open_comp)
            try:
                tag = uuid4().hex[:6]
                emp = await self._employee(s, tag)
                nature = await self._nature(s)
                item = CompanyFinancialItem(
                    tipo="custo_fixo", nome=f"Socio {tag} - Retirada de Capital",
                    valor_referencia=Decimal("20000.00"), category="Custos diversos",
                    is_active=True, start_date=date(2099, 1, 1),
                    cost_center="Administrativo", cost_center_system="ADMINISTRATIVO",
                )
                s.add(item)
                await s.flush()
                svc = CompanyFinanceService(s)
                await svc.replace_entries(
                    item_id=item.id, competencia="2099-01",
                    lancamentos=[{"valor": 15000.0, "vencimento": "2099-01-10", "descricao": None}],
                )
                paid = next(l for l in await self._lines(s, item.id) if l.month == paid_comp)
                paid.amount_paid = paid.amount_final
                paid.paid = True
                await s.flush()

                await svc.update_item(
                    item_id=item.id,
                    data={
                        "item_type": "COLABORADOR_VALOR",
                        "employee_id": emp.id,
                        "payment_component_type_id": nature.id,
                    },
                )
                await s.flush()

                self.assertEqual(item.item_type, CompanyFinancialItemType.COLABORADOR_VALOR)
                self.assertEqual(item.nome, emp.full_name)
                lines = {l.month: l for l in await self._lines(s, item.id) if l.month in (paid_comp, open_comp)}
                # Histórico pago intacto (valor e pagamento); só o rótulo muda.
                self.assertEqual(lines[paid_comp].amount_final, Decimal("15000.00"))
                self.assertEqual(lines[paid_comp].amount_paid, Decimal("15000.00"))
                self.assertTrue(lines[paid_comp].paid)
                for l in lines.values():
                    self.assertEqual(l.name, f"{emp.full_name} — Retirada de Capital")
                    self.assertEqual(l.category, "Colaborador")
                    self.assertEqual(l.type, PayableSnapshotType.FIXED_COST)
                # Mês aberto: valor da REFERÊNCIA (não o custo do colaborador × %).
                self.assertEqual(lines[open_comp].amount_final, Decimal("20000.00"))

                # Fora da média mensal.
                avg = await EmployeesService(s).payroll_averages([emp])
                self.assertNotIn(emp.id, avg)

                # Editar a estrutura de novo (outra categoria do cadastro) não tira da folha.
                await svc.update_item(item_id=item.id, data={"category": "Outra"})
                await s.flush()
                rows = (
                    await s.execute(select(PayableSnapshot.category).where(PayableSnapshot.ref_id == item.id))
                ).scalars().all()
                self.assertEqual(set(rows), {"Colaborador"})
            finally:
                await s.rollback()

    async def test_renomear_colaborador_reflete_no_item_e_em_todos_os_titulos(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.models.company_finance import CompanyFinancialItem
        from app.models.payable_snapshot import PayableSnapshot
        from app.models.payment_component import PaymentComponentType
        from app.services.company_finance_service import CompanyFinanceService
        from app.services.payable_snapshot_service import PayableSnapshotService
        from app.services.payment_variable_component_service import PaymentVariableComponentService

        await engine.dispose()
        paid_comp, open_comp = date(2099, 3, 1), date(2099, 4, 1)
        async with AsyncSessionLocal() as s:
            await self._prelude(s, paid_comp, open_comp)
            try:
                tag = uuid4().hex[:6]
                emp = await self._employee(s, tag)
                old_name = emp.full_name
                nature = await self._nature(s)
                svc = CompanyFinanceService(s)
                item = CompanyFinancialItem(
                    tipo="custo_fixo", nome="qualquer", valor_referencia=Decimal("20000.00"),
                    is_active=True, start_date=date(2099, 3, 1),
                    cost_center="Administrativo", cost_center_system="ADMINISTRATIVO",
                )
                s.add(item)
                await s.flush()
                await svc.update_item(
                    item_id=item.id,
                    data={"item_type": "COLABORADOR_VALOR", "employee_id": emp.id,
                          "payment_component_type_id": nature.id},
                )
                await svc.replace_entries(
                    item_id=item.id, competencia="2099-03",
                    lancamentos=[{"valor": 20000.0, "vencimento": "2099-03-10", "descricao": None}],
                )
                paid = (
                    await s.execute(
                        select(PayableSnapshot).where(
                            PayableSnapshot.ref_id == item.id, PayableSnapshot.month == paid_comp
                        )
                    )
                ).scalar_one()
                paid.amount_paid = paid.amount_final
                paid.paid = True
                reembolso = (
                    await s.execute(select(PaymentComponentType).where(PaymentComponentType.code == "reembolso"))
                ).scalar_one()
                comp = await PaymentVariableComponentService(s).create(
                    {"type_id": reembolso.id, "company_financial_item_id": item.id,
                     "competencia": open_comp, "amount": 300, "note": "Notebook"}
                )
                await s.flush()

                emp.full_name = f"Socio Renomeado {tag}"
                await PayableSnapshotService(s).sync_employee_name(employee_id=emp.id, old_name=old_name)

                await s.refresh(item)
                self.assertEqual(item.nome, emp.full_name)
                rows = (
                    await s.execute(
                        select(PayableSnapshot).where(
                            PayableSnapshot.ref_id.in_([item.id, comp["id"]])
                        )
                    )
                ).scalars().all()
                names = {r.name for r in rows}
                self.assertIn(f"{emp.full_name} — Retirada de Capital", names)
                self.assertIn(f"{emp.full_name} — Reembolso", names)
                self.assertFalse(any(old_name in n for n in names))
                # O título pago só trocou de nome.
                self.assertEqual(paid.amount_paid, Decimal("20000.00"))
                self.assertTrue(paid.paid)
            finally:
                await s.rollback()

    async def test_valor_proprio_exige_colaborador_e_natureza(self) -> None:
        from pydantic import ValidationError

        from app.schemas.company_finance import CompanyFinancialItemCreate, CompanyFinancialItemUpdate

        base = {
            "tipo": "custo_fixo", "nome": "X", "valor_referencia": 1, "cost_center_ref": "ADMINISTRATIVO",
            "start_date": "2099-01-01", "item_type": "COLABORADOR_VALOR",
        }
        with self.assertRaises(ValidationError):
            CompanyFinancialItemCreate(**base, employee_id=uuid4())
        with self.assertRaises(ValidationError):
            CompanyFinancialItemCreate(**base, payment_component_type_id=uuid4())
        ok = CompanyFinancialItemCreate(
            **base, employee_id=uuid4(), payment_component_type_id=uuid4(), percentual=50
        )
        self.assertIsNone(ok.percentual)
        with self.assertRaises(ValidationError):
            CompanyFinancialItemUpdate(item_type="COLABORADOR_VALOR", employee_id=uuid4())

    async def test_manual_continua_sem_colaborador_nem_natureza(self) -> None:
        from app.schemas.company_finance import CompanyFinancialItemCreate

        m = CompanyFinancialItemCreate(
            tipo="custo_fixo", nome="X", valor_referencia=1, cost_center_ref="ADMINISTRATIVO",
            start_date="2099-01-01", employee_id=uuid4(), payment_component_type_id=uuid4(),
        )
        self.assertIsNone(m.employee_id)
        self.assertIsNone(m.payment_component_type_id)


    async def test_retirada_de_capital_nao_e_mao_de_obra_no_resultado(self) -> None:
        from types import SimpleNamespace

        from app.services.company_costs import _item_line

        def item(employee_id, code):
            nature = SimpleNamespace(code=code) if code else None
            return SimpleNamespace(
                id=uuid4(), nome="X", category="Retirada de Capital", employee_id=employee_id,
                payment_component_type=nature, project_cost_group=None, cost_center_project_id=None,
                fleet_allocation=None,
            )

        socio = item(uuid4(), "retirada_capital")
        self.assertFalse(_item_line(socio, amount=1).is_labor)
        # Componente variável (Reembolso) do item do sócio também não vira Mão de obra.
        self.assertFalse(_item_line(socio, amount=1, is_labor=True).is_labor)
        self.assertTrue(_item_line(item(uuid4(), None), amount=1).is_labor)  # matriz
        self.assertTrue(_item_line(item(uuid4(), "ajuda_custo"), amount=1).is_labor)
        self.assertFalse(_item_line(item(None, None), amount=1).is_labor)  # fornecedor


if __name__ == "__main__":
    unittest.main()
