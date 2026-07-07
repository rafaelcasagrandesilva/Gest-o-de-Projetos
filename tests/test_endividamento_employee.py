"""Endividamento vinculado a colaborador + descrição própria (item_description).

Cobre: cadastro sem/com colaborador (nome composto automaticamente), múltiplos
endividamentos por colaborador, geração automática de Contas a Pagar (Credor/Descrição
separados), detalhamento na Folha de Pagamento e compatibilidade com registros legados
(sem employee_id/item_description). Nenhuma regra financeira é alterada.
"""

from __future__ import annotations

import unittest
from datetime import date
from uuid import UUID, uuid4


def _debt_create_data(**over) -> dict:
    """Payload de criação (via schema, exercitando os validators)."""
    from app.schemas.company_finance import CompanyFinancialItemCreate

    base = dict(
        tipo="endividamento",
        item_description="Acordo de Remuneração",
        valor_referencia=3000.0,
        cost_center_ref="FINANCEIRO",
        is_monthly_required=True,
        start_date=date(2099, 1, 1),
    )
    base.update(over)
    return CompanyFinancialItemCreate(**base).model_dump()


class DebtEmployeeSchemaTests(unittest.TestCase):
    def test_compose_debt_nome(self) -> None:
        from app.services.company_finance_service import compose_debt_nome

        self.assertEqual(
            compose_debt_nome("Sigmar Dupre", "Acordo de Remuneração"),
            "Sigmar Dupre - Acordo de Remuneração",
        )
        self.assertEqual(compose_debt_nome(None, "Empréstimo Particular"), "Empréstimo Particular")
        self.assertEqual(compose_debt_nome("Sigmar", None), "Sigmar")

    def test_description_required_for_debt(self) -> None:
        from pydantic import ValidationError

        from app.schemas.company_finance import CompanyFinancialItemCreate

        with self.assertRaises(ValidationError):
            CompanyFinancialItemCreate(
                tipo="endividamento",
                valor_referencia=100.0,
                cost_center_ref="FINANCEIRO",
                start_date=date(2099, 1, 1),
            )

    def test_debt_never_matrix(self) -> None:
        data = _debt_create_data(item_type="COLABORADOR_MATRIZ", percentual=50)
        self.assertEqual(data["item_type"], "MANUAL")
        self.assertIsNone(data["percentual"])

    def test_export_detalhe_formatting(self) -> None:
        from app.services.report_export import _format_endividamentos_detalhe

        um = [{"descricao": "Acordo de Remuneração", "valor": 3000.0}]
        self.assertIn("Acordo de Remuneração", _format_endividamentos_detalhe(um, summarize=True))
        # Único item nunca é resumido.
        self.assertNotIn("endividamentos", _format_endividamentos_detalhe(um, summarize=True))

        varios = [
            {"descricao": "Acordo de Remuneração", "valor": 3000.0},
            {"descricao": "Acerto de Mútuos", "valor": 1500.0},
            {"descricao": "Vale Salarial", "valor": 700.0},
        ]
        # XLSX (summarize=False): completo, com valor individual de cada dívida.
        full = _format_endividamentos_detalhe(varios, summarize=False)
        self.assertIn("Acordo de Remuneração", full)
        self.assertIn("Acerto de Mútuos", full)
        self.assertIn("Vale Salarial", full)
        # PDF (summarize=True) com texto longo → resumo "N endividamentos".
        self.assertEqual(_format_endividamentos_detalhe(varios, summarize=True), "3 endividamentos")
        self.assertEqual(_format_endividamentos_detalhe([], summarize=True), "")


class DebtEmployeeDBTests(unittest.IsolatedAsyncioTestCase):
    async def test_debt_lifecycle_cap_and_payroll(self) -> None:
        from sqlalchemy import select, text
        from sqlalchemy.exc import ProgrammingError

        from app.database.session import AsyncSessionLocal, engine
        from app.models.company_finance import CompanyFinancialItem
        from app.models.employee import Employee
        from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
        from app.services.company_finance_service import CompanyFinanceService
        from app.services.payable_snapshot_service import PayableSnapshotService
        from app.services.report_service import ReportService

        await engine.dispose()
        comp = date(2099, 7, 1)  # competência futura isolada
        tag = uuid4().hex[:6]
        created_item_ids: list[UUID] = []

        async with AsyncSessionLocal() as session:
            try:
                await session.execute(text("SELECT item_description FROM payable_snapshots LIMIT 1"))
            except ProgrammingError:
                self.skipTest("Coluna item_description ausente (rode alembic upgrade head).")

            cf = CompanyFinanceService(session)

            emp = Employee(
                full_name=f"Sigmar {tag}",
                email=f"sigmar_{tag}@ex.com",
                employment_type="CLT",
                is_active=True,
                salary_base=5000.0,
                total_cost=0,
            )
            session.add(emp)
            await session.flush()

            # (1) Endividamento SEM colaborador → nome = descrição.
            it_no_emp = await cf.create_item(
                actor_user_id=uuid4(),
                data=_debt_create_data(item_description=f"Empréstimo Particular {tag}"),
            )
            created_item_ids.append(it_no_emp.id)
            self.assertIsNone(it_no_emp.employee_id)
            self.assertEqual(it_no_emp.item_description, f"Empréstimo Particular {tag}")
            self.assertEqual(it_no_emp.nome, f"Empréstimo Particular {tag}")

            # (2) Endividamento COM colaborador → nome = "<colaborador> - <descrição>".
            it_emp1 = await cf.create_item(
                actor_user_id=uuid4(),
                data=_debt_create_data(
                    item_description=f"Acordo de Remuneração {tag}", employee_id=emp.id
                ),
            )
            created_item_ids.append(it_emp1.id)
            self.assertEqual(it_emp1.employee_id, emp.id)
            self.assertEqual(it_emp1.item_description, f"Acordo de Remuneração {tag}")
            self.assertEqual(it_emp1.nome, f"Sigmar {tag} - Acordo de Remuneração {tag}")

            # (3) Segundo endividamento para o MESMO colaborador → independente.
            it_emp2 = await cf.create_item(
                actor_user_id=uuid4(),
                data=_debt_create_data(
                    item_description=f"Acerto de Mútuos {tag}",
                    employee_id=emp.id,
                    valor_referencia=1500.0,
                ),
            )
            created_item_ids.append(it_emp2.id)
            self.assertEqual(it_emp2.employee_id, emp.id)
            self.assertNotEqual(it_emp1.id, it_emp2.id)
            await session.flush()

            # (4) Geração automática de Contas a Pagar (debt obrigatório gera).
            await PayableSnapshotService(session)._generate_company_finance_payables(payment_month=comp)
            await session.flush()

            snaps = {
                r.ref_id: r
                for r in (
                    await session.execute(
                        select(PayableSnapshot).where(
                            PayableSnapshot.month == comp,
                            PayableSnapshot.ref_id.in_(created_item_ids),
                        )
                    )
                )
                .scalars()
                .all()
            }
            self.assertEqual(set(snaps), set(created_item_ids))

            # Sem colaborador: Credor = descrição; item_description preenchido.
            s0 = snaps[it_no_emp.id]
            self.assertEqual(s0.type, PayableSnapshotType.ENDIVIDAMENTO)
            self.assertEqual(s0.name, f"Empréstimo Particular {tag}")
            self.assertEqual(s0.item_description, f"Empréstimo Particular {tag}")

            # Com colaborador: Credor = colaborador; Descrição separada.
            s1 = snaps[it_emp1.id]
            self.assertEqual(s1.name, f"Sigmar {tag}")
            self.assertEqual(s1.item_description, f"Acordo de Remuneração {tag}")
            self.assertEqual(float(s1.amount_final), 3000.0)

            s2 = snaps[it_emp2.id]
            self.assertEqual(s2.name, f"Sigmar {tag}")
            self.assertEqual(s2.item_description, f"Acerto de Mútuos {tag}")

            # (5) Folha de Pagamento: soma os dois endividamentos + detalhamento individual.
            payload = await ReportService(session).generate_payroll_report(
                competencia=comp, scenario="REALIZADO"
            )
            mine = [r for r in payload["rows"] if r["nome"] == f"Sigmar {tag}"]
            self.assertEqual(len(mine), 1)
            row = mine[0]
            self.assertEqual(row["endividamentos"], 4500.0)  # 3000 + 1500
            itens = {i["descricao"]: i["valor"] for i in row["endividamentos_itens"]}
            self.assertEqual(itens.get(f"Acordo de Remuneração {tag}"), 3000.0)
            self.assertEqual(itens.get(f"Acerto de Mútuos {tag}"), 1500.0)

            # Limpeza (mês de teste é futuro e isolado).
            await session.execute(text("DELETE FROM payable_snapshots WHERE month = :m"), {"m": comp})
            for iid in created_item_ids:
                fresh = await session.get(CompanyFinancialItem, iid)
                if fresh is not None:
                    await session.delete(fresh)
            fresh_emp = await session.get(Employee, emp.id)
            if fresh_emp is not None:
                await session.delete(fresh_emp)
            await session.commit()

    async def test_legacy_debt_preserved(self) -> None:
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        from app.database.session import AsyncSessionLocal, engine
        from app.models.company_finance import CompanyFinancialItem
        from app.models.payable_snapshot import PayableSnapshot
        from app.services.company_finance_service import CompanyFinanceService
        from app.services.payable_snapshot_service import PayableSnapshotService

        await engine.dispose()
        comp = date(2099, 8, 1)
        tag = uuid4().hex[:6]
        legacy_nome = f"SIGMAR DUPRE GUIMARAES (ACORDO DE REMUNERACAO) {tag}"

        async with AsyncSessionLocal() as session:
            try:
                await session.execute(text("SELECT item_description FROM company_financial_items LIMIT 1"))
            except ProgrammingError:
                self.skipTest("Coluna item_description ausente (rode alembic upgrade head).")

            # Registro legado: nome misturado, sem employee_id nem item_description.
            legacy = CompanyFinancialItem(
                tipo="endividamento",
                nome=legacy_nome,
                valor_referencia=2000.0,
                is_active=True,
                is_monthly_required=True,
                start_date=date(2099, 1, 1),
                cost_center="Financeiro",
                cost_center_system="FINANCEIRO",
            )
            session.add(legacy)
            await session.flush()

            # Leitura preserva o dado existente.
            reads = await CompanyFinanceService(session).list_items("endividamento", None)
            mine = [r for r in reads if r["id"] == legacy.id]
            self.assertEqual(len(mine), 1)
            self.assertEqual(mine[0]["nome"], legacy_nome)
            self.assertIsNone(mine[0]["item_description"])

            # CAP: sem colaborador/descrição, Credor = nome legado; item_description None.
            await PayableSnapshotService(session)._generate_company_finance_payables(payment_month=comp)
            await session.flush()
            snap = (
                await session.execute(
                    PayableSnapshot.__table__.select().where(PayableSnapshot.ref_id == legacy.id)
                )
            ).first()
            self.assertIsNotNone(snap)
            self.assertEqual(snap.name, legacy_nome)
            self.assertIsNone(snap.item_description)

            await session.execute(text("DELETE FROM payable_snapshots WHERE month = :m"), {"m": comp})
            fresh = await session.get(CompanyFinancialItem, legacy.id)
            if fresh is not None:
                await session.delete(fresh)
            await session.commit()


if __name__ == "__main__":
    unittest.main()
