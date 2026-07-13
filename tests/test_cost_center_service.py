"""CostCenterService: fonte única dos combos de cadastro (Administrativos ∪ projetos ATIVOS)."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from uuid import uuid4


class CostCenterServiceDBTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_available_cost_centers(self) -> None:
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        from app.core.constants.cost_centers import ADMIN_COST_CENTERS
        from app.database.session import AsyncSessionLocal, engine
        from app.models.project import Project
        from app.services.cost_center_service import CostCenterService

        await engine.dispose()
        tag = uuid4().hex[:6]
        cc_active = f"CC-Active-{tag}"
        cc_closed = f"CC-Closed-{tag}"    # encerrado (closed_at)
        cc_deleted = f"CC-Deleted-{tag}"  # apagado (deleted_at) — como o "Drone"
        cc_inactive = f"CC-Inactive-{tag}"  # is_active = False

        async with AsyncSessionLocal() as s:
            try:
                await s.execute(text("SELECT cost_center FROM projects LIMIT 1"))
            except ProgrammingError:
                self.skipTest("Coluna cost_center ausente (rode alembic upgrade head).")
            try:
                now = datetime.now(timezone.utc)
                s.add(Project(name=f"A-{tag}", cost_center=cc_active, is_active=True))
                s.add(Project(name=f"C-{tag}", cost_center=cc_closed, is_active=True, closed_at=now))
                s.add(Project(name=f"D-{tag}", cost_center=cc_deleted, is_active=False, closed_at=now, deleted_at=now))
                s.add(Project(name=f"I-{tag}", cost_center=cc_inactive, is_active=False))
                await s.flush()

                result = await CostCenterService(s).list_available_cost_centers()

                # Administrativos fixos sempre presentes, primeiro e na ordem canônica.
                self.assertEqual(list(result[: len(ADMIN_COST_CENTERS)]), list(ADMIN_COST_CENTERS))
                # Só o projeto ATIVO entra.
                self.assertIn(cc_active, result)
                self.assertNotIn(cc_closed, result)
                self.assertNotIn(cc_deleted, result)
                self.assertNotIn(cc_inactive, result)
                # Sem duplicatas.
                self.assertEqual(len(result), len(set(result)))
            finally:
                await s.rollback()

    async def test_admin_wins_over_project_with_same_name(self) -> None:
        """Projeto ativo cujo cost_center coincide (case-insensitive) com um administrativo
        não duplica a lista — o administrativo prevalece."""
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        from app.database.session import AsyncSessionLocal, engine
        from app.models.project import Project
        from app.services.cost_center_service import CostCenterService

        await engine.dispose()
        tag = uuid4().hex[:6]

        async with AsyncSessionLocal() as s:
            try:
                await s.execute(text("SELECT cost_center FROM projects LIMIT 1"))
            except ProgrammingError:
                self.skipTest("Coluna cost_center ausente (rode alembic upgrade head).")
            try:
                s.add(Project(name=f"Adm-{tag}", cost_center="administrativo", is_active=True))
                await s.flush()

                result = await CostCenterService(s).list_available_cost_centers()
                lowered = [c.lower() for c in result]
                self.assertEqual(lowered.count("administrativo"), 1)  # não duplica
            finally:
                await s.rollback()


if __name__ == "__main__":
    unittest.main()
