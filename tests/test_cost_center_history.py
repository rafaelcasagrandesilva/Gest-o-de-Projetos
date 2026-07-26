"""Centro de Custo temporal (histórico) — colaboradores e veículos.

Cobre os 7 cenários do spec + a mecânica de change_cost_center (fecha anterior, abre nova,
nunca edita histórico fechado). Testes de banco NÃO commitam (rollback ao final).
"""

from __future__ import annotations

import unittest
from datetime import date
from uuid import uuid4


def _has_cc_history_tables(session):
    from sqlalchemy import text
    from sqlalchemy.exc import ProgrammingError

    async def check():
        try:
            await session.execute(text("SELECT 1 FROM employee_cost_center_history LIMIT 1"))
            await session.execute(text("SELECT cost_center FROM vehicles LIMIT 1"))
            return True
        except ProgrammingError:
            return False

    return check()


class CostCenterHistoryServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_change_cost_center_closes_previous_opens_new(self) -> None:
        from sqlalchemy import select
        from app.database.session import AsyncSessionLocal, engine
        from app.models.employee import Employee
        from app.models.cost_center_history import EmployeeCostCenterHistory
        from app.services.cost_center_history_service import EmployeeCostCenterService

        await engine.dispose()
        tag = uuid4().hex[:6]
        async with AsyncSessionLocal() as s:
            if not await _has_cc_history_tables(s):
                self.skipTest("Tabelas de histórico ausentes (rode alembic upgrade head).")
            try:
                emp = Employee(
                    full_name=f"Hist {tag}", employment_type="PJ", is_active=True,
                    salary_base=1000.0, total_cost=0, cost_center=f"CC-A-{tag}",
                )
                s.add(emp)
                await s.flush()
                svc = EmployeeCostCenterService(s)
                await svc.ensure_initial_history(emp)

                await svc.change_cost_center(emp, f"CC-B-{tag}", date(2026, 8, 1))
                rows = (
                    await s.execute(
                        select(EmployeeCostCenterHistory)
                        .where(EmployeeCostCenterHistory.employee_id == emp.id)
                        .order_by(EmployeeCostCenterHistory.start_date)
                    )
                ).scalars().all()
                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[0].cost_center, f"CC-A-{tag}")
                self.assertEqual(rows[0].end_date, date(2026, 7, 31))  # fechado no fim de julho
                self.assertEqual(rows[1].cost_center, f"CC-B-{tag}")
                self.assertEqual(rows[1].start_date, date(2026, 8, 1))
                self.assertIsNone(rows[1].end_date)  # nova linha aberta

                # Resolução por competência.
                self.assertEqual(await svc.get_cost_center(emp.id, date(2026, 3, 1)), f"CC-A-{tag}")
                self.assertEqual(await svc.get_cost_center(emp.id, date(2026, 8, 1)), f"CC-B-{tag}")
            finally:
                await s.rollback()


class CostCenterHistoryScenariosTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        await engine.dispose()
        self.s = AsyncSessionLocal()
        await self.s.__aenter__()
        if not await _has_cc_history_tables(self.s):
            await self.s.__aexit__(None, None, None)
            self.skipTest("Tabelas de histórico ausentes (rode alembic upgrade head).")
        self.tag = uuid4().hex[:6]

    async def asyncTearDown(self) -> None:
        await self.s.rollback()
        await self.s.__aexit__(None, None, None)

    async def _project(self, cc):
        from app.models.project import Project
        p = Project(name=f"Proj {cc} {self.tag}", cost_center=cc, is_active=True)
        self.s.add(p)
        await self.s.flush()
        return p

    async def _employee(self, name, cost_center, shared=False):
        from app.models.employee import Employee
        from app.services.cost_center_history_service import EmployeeCostCenterService
        e = Employee(
            full_name=f"{name} {self.tag}", employment_type="PJ", is_active=True,
            salary_base=1000.0, total_cost=0, cost_center=cost_center,
            can_allocate_other_cost_centers=shared, start_date=date(2099, 1, 1),
        )
        self.s.add(e)
        await self.s.flush()
        await EmployeeCostCenterService(self.s).ensure_initial_history(e)
        return e

    async def _emp_appears(self, project, competence):
        from app.modules.employees.router import list_employees as endpoint
        reads = await endpoint(
            db=self.s, search=self.tag, project_id=project.id, offset=0, limit=200, competencia=competence
        )
        return {r.id for r in reads}

    # 1 + 5 — colaborador muda de centro; compartilhado sempre aparece
    async def test_employee_temporal_and_shared(self) -> None:
        cc_a, cc_b = f"CC-A-{self.tag}", f"CC-B-{self.tag}"
        from app.services.cost_center_history_service import EmployeeCostCenterService
        emp = await self._employee("Emp", cc_a)
        await EmployeeCostCenterService(self.s).change_cost_center(emp, cc_b, date(2026, 8, 1))
        shared = await self._employee("Shared", cc_a, shared=True)
        proj_a = await self._project(cc_a)
        proj_b = await self._project(cc_b)

        self.assertIn(emp.id, await self._emp_appears(proj_a, date(2026, 3, 1)))     # mar: CC-A
        self.assertNotIn(emp.id, await self._emp_appears(proj_b, date(2026, 3, 1)))  # mar: não em CC-B
        self.assertIn(emp.id, await self._emp_appears(proj_b, date(2026, 8, 1)))     # ago: CC-B
        self.assertNotIn(emp.id, await self._emp_appears(proj_a, date(2026, 8, 1)))  # ago: não em CC-A
        # compartilhado aparece em qualquer projeto/competência
        self.assertIn(shared.id, await self._emp_appears(proj_b, date(2026, 3, 1)))
        self.assertIn(shared.id, await self._emp_appears(proj_a, date(2026, 8, 1)))

    # 3 — colaborador sem centro aparece em qualquer projeto
    async def test_employee_without_cost_center(self) -> None:
        null_emp = await self._employee("Null", None)
        proj = await self._project(f"CC-X-{self.tag}")
        self.assertIn(null_emp.id, await self._emp_appears(proj, date(2026, 3, 1)))
        self.assertIn(null_emp.id, await self._emp_appears(proj, date(2026, 12, 1)))

    # 6 — Folha: março usa centro antigo; agosto, o novo
    async def test_payroll_temporal_cost_center(self) -> None:
        from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
        from app.services.cost_center_history_service import EmployeeCostCenterService
        from app.services.report_service import ReportService
        cc_a, cc_b = f"CC-A-{self.tag}", f"CC-B-{self.tag}"
        emp = await self._employee("Folha", cc_a)
        await EmployeeCostCenterService(self.s).change_cost_center(emp, cc_b, date(2026, 8, 1))
        # O relatório consolida o CAP: cria o lançamento de folha no mês de PAGAMENTO
        # (competência trabalhada + 1). O Centro de Custo exibido é o vigente na competência
        # trabalhada (março → antigo; agosto → novo).
        for pay in (date(2026, 4, 1), date(2026, 9, 1)):
            self.s.add(PayableSnapshot(
                month=pay, type=PayableSnapshotType.COLLABORATOR, ref_id=emp.id,
                name=emp.full_name, cost_center="Projeto", category="Mão de obra",
                amount_original=1000.0, amount_final=1000.0, amount_paid=0,
                due_date=date(pay.year, pay.month, 10), paid=False,
            ))
        await self.s.flush()
        rpt_mar = await ReportService(self.s).generate_payroll_report(competencia=date(2026, 3, 1), scenario="REALIZADO")
        rpt_ago = await ReportService(self.s).generate_payroll_report(competencia=date(2026, 8, 1), scenario="REALIZADO")
        row_mar = next(r for r in rpt_mar["rows"] if r["nome"] == emp.full_name)
        row_ago = next(r for r in rpt_ago["rows"] if r["nome"] == emp.full_name)
        self.assertEqual(row_mar["centro_custo"], cc_a)  # março: centro antigo
        self.assertEqual(row_ago["centro_custo"], cc_b)  # agosto: centro novo

    # 7 — compatibilidade: colaborador com histórico "desde 1900" (backfill) funciona
    async def test_backfill_compatibility(self) -> None:
        cc = f"CC-Compat-{self.tag}"
        emp = await self._employee("Compat", cc)  # ensure_initial_history = start 1900
        proj = await self._project(cc)
        self.assertIn(emp.id, await self._emp_appears(proj, date(2020, 1, 1)))
        self.assertIn(emp.id, await self._emp_appears(proj, date(2099, 1, 1)))


class VehicleCostCenterHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def _setup_session(self):
        from app.database.session import AsyncSessionLocal, engine
        await engine.dispose()
        s = AsyncSessionLocal()
        await s.__aenter__()
        if not await _has_cc_history_tables(s):
            await s.__aexit__(None, None, None)
            self.skipTest("Tabelas de histórico ausentes (rode alembic upgrade head).")
        return s

    async def _vehicle(self, s, plate, cost_center):
        from app.models.fleet import Vehicle
        from app.services.cost_center_history_service import VehicleCostCenterService
        v = Vehicle(plate=plate, vehicle_type="LIGHT", monthly_cost=0, is_active=True, cost_center=cost_center)
        s.add(v)
        await s.flush()
        await VehicleCostCenterService(s).ensure_initial_history(v)
        return v

    async def _plates_for_project(self, s, project, competence):
        from app.services.fleet_service import FleetService
        rows = await FleetService(s).list_active_for_project(
            project_id=project.id, competencia=competence, offset=0, limit=500
        )
        return {v.id for v in rows}

    # 2 — veículo muda de centro; 4 — veículo sem centro aparece em qualquer projeto
    async def test_vehicle_temporal_and_null(self) -> None:
        from app.models.project import Project
        from app.services.cost_center_history_service import VehicleCostCenterService
        s = await self._setup_session()
        tag = uuid4().hex[:6]
        try:
            cc_a, cc_b = f"CC-A-{tag}", f"CC-B-{tag}"
            v = await self._vehicle(s, f"AAA{tag[:4]}", cc_a)
            await VehicleCostCenterService(s).change_cost_center(v, cc_b, date(2026, 8, 1))
            v_null = await self._vehicle(s, f"NUL{tag[:4]}", None)
            proj_a = Project(name=f"PA {tag}", cost_center=cc_a, is_active=True)
            proj_b = Project(name=f"PB {tag}", cost_center=cc_b, is_active=True)
            s.add(proj_a); s.add(proj_b)
            await s.flush()

            self.assertIn(v.id, await self._plates_for_project(s, proj_a, date(2026, 3, 1)))      # mar: CC-A
            self.assertNotIn(v.id, await self._plates_for_project(s, proj_b, date(2026, 3, 1)))
            self.assertIn(v.id, await self._plates_for_project(s, proj_b, date(2026, 8, 1)))      # ago: CC-B
            self.assertNotIn(v.id, await self._plates_for_project(s, proj_a, date(2026, 8, 1)))
            # veículo sem centro aparece em qualquer projeto/competência
            self.assertIn(v_null.id, await self._plates_for_project(s, proj_a, date(2026, 3, 1)))
            self.assertIn(v_null.id, await self._plates_for_project(s, proj_b, date(2026, 8, 1)))
        finally:
            await s.rollback()
            await s.__aexit__(None, None, None)


if __name__ == "__main__":
    unittest.main()
