"""Centro de Custo do colaborador: filtro por projeto + folha só com movimentação."""

from __future__ import annotations

import unittest
from datetime import date
from uuid import uuid4


class EmployeeCostCenterDBTests(unittest.IsolatedAsyncioTestCase):
    async def test_filter_and_payroll_movement(self) -> None:
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        from app.database.session import AsyncSessionLocal, engine
        from app.models.employee import Employee
        from app.models.employee_monthly_payroll_override import EmployeeMonthlyPayrollOverride
        from app.models.project import Project
        from app.services.employees_service import EmployeesService
        from app.services.report_service import ReportService

        await engine.dispose()
        tag = uuid4().hex[:6]
        cc_x = f"CC-X-{tag}"
        cc_y = f"CC-Y-{tag}"

        async with AsyncSessionLocal() as s:
            try:
                await s.execute(text("SELECT cost_center FROM employees LIMIT 1"))
            except ProgrammingError:
                self.skipTest("Coluna cost_center ausente (rode alembic upgrade head).")

            # Projeto SEM cost_center → efetivo cai para o NOME.
            proj_named = Project(name=cc_x, is_active=True)
            # Projeto COM cost_center explícito.
            proj_cc = Project(name=f"Proj {tag}", cost_center=cc_x, is_active=True)
            s.add(proj_named)
            s.add(proj_cc)
            await s.flush()

            def mk(name, cc, shared=False):
                return Employee(
                    full_name=f"CC {tag} {name}",
                    employment_type="PJ",
                    is_active=True,
                    salary_base=1000.0,
                    total_cost=0,
                    start_date=date(2099, 1, 1),
                    cost_center=cc,
                    can_allocate_other_cost_centers=shared,
                )

            e_match = mk("match", cc_x)
            e_other = mk("other", cc_y)
            e_shared = mk("shared", cc_y, shared=True)
            e_null = mk("null", None)
            for e in (e_match, e_other, e_shared, e_null):
                s.add(e)
            await s.flush()

            svc = EmployeesService(s)

            # cost_center_for_project: usa nome quando não há cost_center; usa cost_center quando há.
            self.assertEqual(await svc.cost_center_for_project(proj_named.id), cc_x)
            self.assertEqual(await svc.cost_center_for_project(proj_cc.id), cc_x)

            # Filtro por Centro de Custo do projeto: match + compartilhado + não classificado (NULL).
            rows = await svc.list_employees(search=f"CC {tag}", cost_center=cc_x, limit=50)
            names = {r.full_name for r in rows}
            self.assertIn(e_match.full_name, names)      # mesmo centro
            self.assertIn(e_shared.full_name, names)     # compartilhado
            self.assertIn(e_null.full_name, names)       # não classificado (compat)
            self.assertNotIn(e_other.full_name, names)   # outro centro → escondido

            # Sem filtro (project_id ausente): mostra todos.
            rows_all = await svc.list_employees(search=f"CC {tag}", cost_center=None, limit=50)
            self.assertEqual(len({r.full_name for r in rows_all}), 4)

            # --- Folha: somente colaboradores com MOVIMENTAÇÃO na competência ---
            comp = date(2099, 7, 1)
            # e_match: cria holerite → deve aparecer. e_null: sem movimentação → não aparece.
            s.add(
                EmployeeMonthlyPayrollOverride(
                    employee_id=e_match.id, competence_month="2099-07",
                    net_salary_amount=1234.0, vr_amount=0.0,
                )
            )
            await s.flush()

            report = await ReportService(s).generate_payroll_report(competencia=comp, scenario="REALIZADO")
            report_names = {r["nome"] for r in report["rows"]}
            self.assertIn(e_match.full_name, report_names)     # tem holerite
            self.assertNotIn(e_null.full_name, report_names)   # sem movimentação
            self.assertNotIn(e_other.full_name, report_names)
            # Coluna Centro de Custo reflete o cadastro.
            match_row = next(r for r in report["rows"] if r["nome"] == e_match.full_name)
            self.assertEqual(match_row["centro_custo"], cc_x)

            # Limpeza.
            await s.execute(
                text("DELETE FROM employee_monthly_payroll_overrides WHERE employee_id = :e"),
                {"e": str(e_match.id)},
            )
            for e in (e_match, e_other, e_shared, e_null):
                fresh = await s.get(Employee, e.id)
                if fresh is not None:
                    await s.delete(fresh)
            for p in (proj_named, proj_cc):
                fresh = await s.get(Project, p.id)
                if fresh is not None:
                    await s.delete(fresh)
            await s.commit()


if __name__ == "__main__":
    unittest.main()
