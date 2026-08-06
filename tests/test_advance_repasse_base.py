"""Repasse (perfil LEPTA) = 7% do ANTECIPADO da operação (= "Nominal" do borderô).

O antecipado reflete a BASE escolhida por NF (Bruto/Líquido/Líquido-10%), que é o valor que a
LEPTA usa como Nominal. Validado nos borderôs reais (ex.: #11417 base Bruto → 30.100; #11554 base
Líquido → 12.323,99). Teste de banco NÃO commita (rollback ao final).
"""

from __future__ import annotations

import unittest
from datetime import date
from uuid import uuid4


class RepasseBaseTests(unittest.IsolatedAsyncioTestCase):
    async def _lepta_and_invoices(self, s):
        from sqlalchemy import select
        from sqlalchemy.exc import ProgrammingError
        from app.models.advance_institution import AdvanceInstitution
        from app.models.project import Project
        from app.models.receivable import ReceivableInvoice

        try:
            lepta = (
                await s.execute(select(AdvanceInstitution).where(AdvanceInstitution.operation_profile == "LEPTA"))
            ).scalars().first()
        except ProgrammingError:
            self.skipTest("Tabela advance_institutions ausente (rode alembic upgrade head).")
        if lepta is None:
            self.skipTest("Nenhuma instituição com perfil LEPTA no ambiente.")
        proj = Project(name=f"repasse {uuid4().hex[:8]}", is_active=True)
        s.add(proj)
        await s.flush()
        invs = []
        for i in range(2):  # 2 NFs: bruto 100.000 / líquido 80.000 cada.
            inv = ReceivableInvoice(
                nf_number=f"RP-{uuid4().hex[:6]}-{i}", project_id=proj.id,
                issue_date=date(2026, 5, 1), due_days=30, due_date=date(2026, 6, 1),
                gross_amount=100000.0, net_amount=80000.0, received_amount=0.0, invoice_status="EMITIDA",
            )
            s.add(inv)
            invs.append(inv)
        await s.flush()
        return lepta, invs

    async def _repasse_for_basis(self, basis: str) -> float:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.receivable_advance_batch_service import ReceivableAdvanceBatchService

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            try:
                lepta, invs = await self._lepta_and_invoices(s)
                svc = ReceivableAdvanceBatchService(s)
                batch = await svc.create_batch(
                    institution_id=lepta.id, received_amount=0.0, discount_amount=0.0, fee_amount=0.0,
                    repasse_enabled=True, receive_date=date(2026, 6, 10), repayment_date=date(2026, 7, 10),
                    observation=None,
                    items_config=[{"invoice_id": iv.id, "advance_basis": basis} for iv in invs],
                    created_by_id=None,
                )
                await svc.confirm_batch(batch_id=batch.id)
                await s.flush()
                return float(batch.repasse_amount)
            finally:
                await s.rollback()

    async def test_repasse_follows_antecipado_bruto_base(self) -> None:
        # Base BRUTO → antecipado = bruto (200.000) → repasse 7% = 14.000,00 (NÃO 11.200 do líquido).
        rep = await self._repasse_for_basis("BRUTO")
        self.assertEqual(rep, 14000.0)

    async def test_repasse_follows_antecipado_liquido_base(self) -> None:
        # Base LÍQUIDO → antecipado = líquido (160.000) → repasse 7% = 11.200,00.
        rep = await self._repasse_for_basis("LIQUIDO")
        self.assertEqual(rep, 11200.0)
