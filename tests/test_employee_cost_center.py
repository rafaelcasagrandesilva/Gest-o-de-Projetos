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
        from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
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

            # Centro de Custo agora é temporal — cria o histórico inicial (como no backfill/
            # no serviço). Colaboradores criados direto via ORM precisam disso nos testes.
            from app.services.cost_center_history_service import EmployeeCostCenterService

            cchs = EmployeeCostCenterService(s)
            for e in (e_match, e_other, e_shared, e_null):
                await cchs.ensure_initial_history(e)

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

            # --- Folha: só quem tem lançamento no CAP (mês de pagamento) aparece ---
            comp = date(2099, 7, 1)  # competência trabalhada; paga no CAP de 2099-08
            # e_match: tem folha no CAP → aparece. e_null/e_other: sem lançamento → não aparecem.
            s.add(
                PayableSnapshot(
                    month=date(2099, 8, 1), type=PayableSnapshotType.COLLABORATOR,
                    ref_id=e_match.id, name=e_match.full_name, cost_center="Projeto",
                    category="Mão de obra", amount_original=1234.0, amount_final=1234.0,
                    amount_paid=0, due_date=date(2099, 8, 10), paid=False,
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
                text("DELETE FROM payable_snapshots WHERE ref_id = :e"),
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


class CostCenterVocabularyDBTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_cost_centers_is_admin_plus_active_projects(self) -> None:
        """Nova arquitetura: a lista = Administrativos fixos ∪ `projects.cost_center` de projetos
        ATIVOS. NÃO inclui nome de projeto, NÃO inclui `employees.cost_center`, e NÃO inclui
        Centro de Custo de projeto encerrado/apagado (regressão do "Drone")."""
        from datetime import datetime, timezone

        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        from app.core.constants.cost_centers import ADMIN_COST_CENTERS
        from app.database.session import AsyncSessionLocal, engine
        from app.models.employee import Employee
        from app.models.project import Project
        from app.modules.collaborators.router import list_cost_centers

        await engine.dispose()
        tag = uuid4().hex[:6]
        proj_name_only = f"ProjSemCC-{tag}"  # projeto sem cost_center → nada a listar
        cc_active = f"CC-Active-{tag}"
        cc_closed = f"CC-Closed-{tag}"  # simula o "Drone": projeto encerrado+apagado
        cc_emp = f"CC-Emp-{tag}"

        async with AsyncSessionLocal() as s:
            try:
                await s.execute(text("SELECT cost_center FROM employees LIMIT 1"))
            except ProgrammingError:
                self.skipTest("Coluna cost_center ausente (rode alembic upgrade head).")
            try:
                now = datetime.now(timezone.utc)
                s.add(Project(name=proj_name_only, is_active=True))
                s.add(Project(name=f"Proj-{tag}", cost_center=cc_active, is_active=True))
                # Encerrado E apagado (como "Drone") → não pode aparecer.
                s.add(
                    Project(
                        name=cc_closed, cost_center=cc_closed,
                        is_active=False, closed_at=now, deleted_at=now,
                    )
                )
                s.add(
                    Employee(
                        full_name=f"Emp CC {tag}",
                        employment_type="PJ",
                        is_active=True,
                        salary_base=1000.0,
                        total_cost=0,
                        cost_center=cc_emp,
                    )
                )
                await s.flush()

                result = await list_cost_centers(db=s)
                self.assertIn(cc_active, result)              # projeto ativo entra
                self.assertNotIn(cc_closed, result)           # encerrado/apagado NÃO entra
                self.assertNotIn(proj_name_only, result)      # nome de projeto NÃO entra
                self.assertNotIn(cc_emp, result)              # employees.cost_center NÃO é mais fonte
                for admin in ADMIN_COST_CENTERS:              # administrativos sempre presentes
                    self.assertIn(admin, result)
                # Administrativos vêm primeiro, na ordem canônica.
                self.assertEqual(list(result[: len(ADMIN_COST_CENTERS)]), list(ADMIN_COST_CENTERS))
            finally:
                await s.rollback()  # não persiste dados de teste


class EmployeesEndpointFilterDBTests(unittest.IsolatedAsyncioTestCase):
    async def test_employees_endpoint_applies_project_filter(self) -> None:
        """O handler REAL de GET /employees (o que o frontend chama) aplica o filtro por
        Centro de Custo do projeto — guarda contra a regressão em que o project_id era
        ignorado e todos os colaboradores voltavam."""
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        from app.database.session import AsyncSessionLocal, engine
        from app.models.employee import Employee
        from app.models.project import Project
        from app.modules.employees.router import list_employees as employees_endpoint

        await engine.dispose()
        tag = uuid4().hex[:6]
        cc_x = f"CC-X-{tag}"
        comp = date(2099, 7, 1)

        async with AsyncSessionLocal() as s:
            try:
                await s.execute(text("SELECT cost_center FROM employees LIMIT 1"))
            except ProgrammingError:
                self.skipTest("Coluna cost_center ausente (rode alembic upgrade head).")
            try:
                proj = Project(name=f"Proj {tag}", cost_center=cc_x, is_active=True)
                s.add(proj)

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
                e_other = mk("other", f"CC-Y-{tag}")
                e_null = mk("null", None)
                for e in (e_match, e_other, e_null):
                    s.add(e)
                await s.flush()

                from app.services.cost_center_history_service import EmployeeCostCenterService

                cchs = EmployeeCostCenterService(s)
                for e in (e_match, e_other, e_null):
                    await cchs.ensure_initial_history(e)

                # Chama o handler real do endpoint /employees, com project_id (como o frontend).
                reads = await employees_endpoint(
                    db=s,
                    search=f"CC {tag}",
                    project_id=proj.id,
                    offset=0,
                    limit=50,
                    competencia=comp,
                )
                names = {r.full_name for r in reads}
                self.assertIn(e_match.full_name, names)      # mesmo centro → aparece
                self.assertIn(e_null.full_name, names)       # sem centro → aparece
                self.assertNotIn(e_other.full_name, names)   # centro diferente → NÃO aparece

                # Sem project_id → sem filtro (todos aparecem).
                reads_all = await employees_endpoint(
                    db=s, search=f"CC {tag}", project_id=None, offset=0, limit=50, competencia=comp
                )
                self.assertEqual(len({r.full_name for r in reads_all}), 3)
            finally:
                await s.rollback()


if __name__ == "__main__":
    unittest.main()
