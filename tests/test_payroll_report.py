"""Relatório Folha de Pagamento (novo): consolidação por colaborador + Excel/PDF.

Não altera o relatório de Colaboradores nem cálculos existentes — apenas lê os dados.
"""

from __future__ import annotations

import io
import unittest
from datetime import date
from uuid import uuid4

from app.services.report_service import _debt_monthly_value, _payroll_distribution_label


class _Slice:
    def __init__(self, name, pct):
        self.project_name = name
        self.allocation_percentage = pct


class _Line:
    def __init__(self, slices, admin=0.0):
        self.by_project = slices
        self.administrative_cost = admin


class PayrollHelperTests(unittest.TestCase):
    def test_distribution_labels(self) -> None:
        self.assertEqual(_payroll_distribution_label(None), "—")
        self.assertEqual(_payroll_distribution_label(_Line([_Slice("Fiscalização AT", 100)])), "Fiscalização AT (100%)")
        self.assertEqual(
            _payroll_distribution_label(_Line([_Slice("Fiscalização AT", 50)])),
            "Fiscalização AT (50%) / Administrativo (50%)",
        )
        self.assertEqual(_payroll_distribution_label(_Line([], admin=1200.0)), "Administrativo")
        self.assertEqual(_payroll_distribution_label(_Line([], admin=0.0)), "—")

    def test_debt_monthly_value(self) -> None:
        class D:
            has_renegotiation = True
            renegotiation_type = "INSTALLMENTS"
            installment_value = 500.0
            renegotiated_amount = 6000.0
            valor_referencia = 12000.0

        self.assertEqual(_debt_monthly_value(D()), 500.0)

        class R:
            has_renegotiation = False
            renegotiation_type = None
            installment_value = None
            renegotiated_amount = None
            valor_referencia = 900.0

        self.assertEqual(_debt_monthly_value(R()), 900.0)


class PayrollReportDBTests(unittest.IsolatedAsyncioTestCase):
    async def test_consolidation_and_exports(self) -> None:
        from sqlalchemy import select, text
        from sqlalchemy.exc import ProgrammingError

        from app.database.session import AsyncSessionLocal, engine
        from app.models.company_finance import CompanyFinancialItem
        from app.models.employee import Employee
        from app.models.employee_monthly_payroll_override import EmployeeMonthlyPayrollOverride
        from app.services.export.report_meta import ReportContext
        from app.services.report_export import render_report_bytes
        from app.services.report_service import ReportService

        await engine.dispose()
        comp = date(2099, 6, 1)
        tag = uuid4().hex[:6]

        async with AsyncSessionLocal() as session:
            try:
                await session.execute(text("SELECT 1 FROM employee_monthly_payroll_overrides LIMIT 1"))
            except ProgrammingError:
                self.skipTest("Tabelas ausentes (rode alembic upgrade head).")

            emp = Employee(
                full_name=f"Folha CLT {tag}",
                email=f"folha_{tag}@ex.com",
                employment_type="CLT",
                is_active=True,
                salary_base=5000.0,
                total_cost=0,
                pix_key_type="CPF",
                pix_key="000.000.000-00",
            )
            session.add(emp)
            await session.flush()

            session.add(
                EmployeeMonthlyPayrollOverride(
                    employee_id=emp.id,
                    competence_month="2099-06",
                    net_salary_amount=4200.00,
                    vr_amount=600.00,
                )
            )
            session.add(
                CompanyFinancialItem(
                    tipo="endividamento",
                    nome=f"Adiantamento {tag}",
                    valor_referencia=300.0,
                    employee_id=emp.id,
                    is_active=True,
                    start_date=date(2099, 1, 1),
                )
            )
            await session.flush()

            svc = ReportService(session)
            payload = await svc.generate_payroll_report(competencia=comp, scenario="REALIZADO")
            rows = payload["rows"]

            mine = [r for r in rows if r["nome"] == f"Folha CLT {tag}"]
            self.assertEqual(len(mine), 1, "deve haver exatamente 1 linha por colaborador")
            r = mine[0]
            self.assertEqual(r["tipo"], "CLT")
            self.assertEqual(r["salario_liquido"], 4200.00)   # holerite real
            self.assertEqual(r["vr"], 600.00)                  # VR real
            self.assertEqual(r["endividamentos"], 300.00)      # endividamento vinculado
            self.assertIsNone(r["beneficios"])                 # sem módulo de benefícios ainda
            self.assertEqual(r["total_folha"], 4200.00 + 600.00 + 300.00)
            self.assertEqual(r["pix_tipo"], "CPF")

            # Exportações válidas (Excel/PDF).
            ctx = ReportContext(report_type="payroll", generated_by="Teste", filters={"competencia": "2099-06"})
            xlsx, xname, _ = render_report_bytes("payroll", payload, "xlsx", ctx)
            pdf, pname, _ = render_report_bytes("payroll", payload, "pdf", ctx)
            self.assertTrue(xlsx[:2] == b"PK", "xlsx inválido")
            self.assertTrue(pdf[:4] == b"%PDF", "pdf inválido")
            self.assertIn("Folha de Pagamento", xname)

            # Excel deve conter a linha de TOTAIS.
            from openpyxl import load_workbook

            wb = load_workbook(io.BytesIO(xlsx))
            ws = wb.active
            col_a = [str(c.value) for c in ws["A"] if c.value is not None]
            self.assertIn("TOTAIS", col_a)

            # Limpeza.
            await session.execute(
                text("DELETE FROM employee_monthly_payroll_overrides WHERE employee_id = :e"), {"e": str(emp.id)}
            )
            await session.execute(
                text("DELETE FROM company_financial_items WHERE employee_id = :e"), {"e": str(emp.id)}
            )
            fresh = await session.get(Employee, emp.id)
            if fresh is not None:
                await session.delete(fresh)
            await session.commit()


if __name__ == "__main__":
    unittest.main()
