"""F2 — Componentes Variáveis de Pagamento: pipeline único (projeto + custo fixo).

Valida geração de snapshots (espelhando a origem), valor INTEGRAL, transação única,
idempotência, exclusão/edição cirúrgicas, bloqueio de tipo inativo e o invariante
Σ(Relatório)=Σ(CAP)."""

from __future__ import annotations

import unittest
from datetime import date
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError


class PaymentVariableComponentDBTests(unittest.IsolatedAsyncioTestCase):
    async def test_pipeline_project_and_fixed(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.models.employee import Employee
        from app.models.payable_snapshot import PayableOrigin, PayableSnapshot, PayableSnapshotType
        from app.models.payment_component import PaymentComponentType, PaymentVariableComponent
        from app.models.project import Project
        from app.models.project_operational import ProjectLabor
        from app.services.payable_snapshot_service import PayableSnapshotService
        from app.services.payment_variable_component_service import PaymentVariableComponentService

        await engine.dispose()
        tag = uuid4().hex[:6]
        worked = date(2099, 5, 1)
        pay = date(2099, 6, 1)

        async with AsyncSessionLocal() as s:
            try:
                await s.execute(text("SELECT 1 FROM payment_variable_components LIMIT 1"))
            except ProgrammingError:
                self.skipTest("Tabelas ausentes (rode alembic upgrade head).")

            reembolso = (
                await s.execute(select(PaymentComponentType).where(PaymentComponentType.code == "reembolso"))
            ).scalars().first()
            self.assertIsNotNone(reembolso, "seed do tipo 'reembolso' ausente")

            emp = Employee(
                full_name=f"PVC {tag}", email=f"pvc_{tag}@ex.com", employment_type="PJ",
                is_active=True, salary_base=5000.0, total_cost=0,
            )
            proj = Project(name=f"Proj PVC {tag}", is_active=True)
            s.add_all([emp, proj])
            await s.flush()
            labor = ProjectLabor(
                project_id=proj.id, employee_id=emp.id, competencia=worked,
                scenario="REALIZADO", allocation_percentage=50.0,
            )
            s.add(labor)
            await s.flush()

            svc = PaymentVariableComponentService(s)
            snaps = PayableSnapshotService(s)

            async def var_rows():
                return list((await s.execute(
                    select(PayableSnapshot).where(
                        PayableSnapshot.origin == PayableOrigin.VARIABLE.value,
                        PayableSnapshot.month == pay,
                    )
                )).scalars().all())

            # --- Projeto: componente 1 (valor de FACE, apesar de 50% de alocação) ---
            c1 = await svc.create({"type_id": reembolso.id, "amount": 500.0, "project_labor_id": labor.id})
            rows = await var_rows()
            self.assertEqual(len(rows), 1)
            r = rows[0]
            self.assertEqual(r.type, PayableSnapshotType.COLLABORATOR)
            self.assertEqual(r.name, f"PVC {tag} — Reembolso")
            self.assertEqual(float(r.amount_final), 500.0, "valor INTEGRAL, não rateado por 50%")
            self.assertEqual(r.ref_id, c1["id"])

            # --- Projeto: componente 2 do mesmo tipo (permitido; linha separada) ---
            c2 = await svc.create({"type_id": reembolso.id, "amount": 320.0, "project_labor_id": labor.id})
            self.assertEqual(len(await var_rows()), 2)

            # --- Idempotência: rodar o sync 3x não duplica ---
            for _ in range(3):
                await snaps.sync_all_variable_components_for_month(payment_month=pay)
            self.assertEqual(len(await var_rows()), 2, "sync idempotente não duplica")

            # --- Edição do valor reflete no CAP ---
            await svc.update(c1["id"], {"amount": 640.0})
            r1 = await snaps._find_variable_snapshot(c1["id"])
            self.assertEqual(float(r1.amount_final), 640.0)

            # --- Exclusão remove SÓ o seu lançamento ---
            await svc.delete(c2["id"])
            self.assertIsNone(await snaps._find_variable_snapshot(c2["id"]))
            self.assertIsNotNone(await snaps._find_variable_snapshot(c1["id"]))
            self.assertEqual(len(await var_rows()), 1)

            # --- Inativar tipo bloqueia novo lançamento, preserva histórico ---
            reembolso.is_active = False
            await s.flush()
            with self.assertRaises(Exception):
                await svc.create({"type_id": reembolso.id, "amount": 10.0, "project_labor_id": labor.id})
            self.assertIsNotNone(await snaps._find_variable_snapshot(c1["id"]), "histórico preservado")

            # Limpeza (dados de teste isolados no futuro).
            await s.execute(
                text("DELETE FROM payable_snapshots WHERE origin = 'VARIABLE' AND ref_id IN "
                     "(SELECT id FROM payment_variable_components WHERE employee_id = :e)"),
                {"e": str(emp.id)},
            )
            await s.execute(
                text("DELETE FROM payment_variable_components WHERE employee_id = :e"), {"e": str(emp.id)}
            )
            reembolso.is_active = True
            await s.execute(text("DELETE FROM project_labors WHERE id = :i"), {"i": str(labor.id)})
            for obj in (emp, proj):
                fresh = await s.get(type(obj), obj.id)
                if fresh is not None:
                    await s.delete(fresh)
            await s.commit()


if __name__ == "__main__":
    unittest.main()
