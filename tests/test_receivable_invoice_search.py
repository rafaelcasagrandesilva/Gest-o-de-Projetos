"""NFs — busca geral por palavras (nº da NF, cliente, projeto, observações), sem acento.

A busca alimenta lista E cards (mesmo `_apply_filters`), então basta validar a lista.
Teste de banco NÃO commita (rollback ao final).
"""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from uuid import uuid4


class ReceivableInvoiceSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_busca_por_numero_cliente_projeto_e_sem_acento(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.models.project import Project
        from app.models.receivable import ReceivableInvoice
        from app.services.receivable_service import ReceivableService

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            try:
                tag = uuid4().hex[:6]
                proj = Project(name=f"Fiscalização Teste {tag}", is_active=True)
                s.add(proj)
                await s.flush()
                nf = f"98{tag[:4]}"
                s.add(
                    ReceivableInvoice(
                        project_id=proj.id, nf_number=nf, issue_date=date(2099, 6, 5), due_days=90,
                        due_date=date(2099, 9, 3), gross_amount=Decimal("100"), net_amount=Decimal("90"),
                        client_name=f"Cliente São João {tag}", notes="medição extra",
                    )
                )
                await s.flush()
                svc = ReceivableService(s)

                async def numbers(q: str) -> set[str]:
                    rows = await svc.list_invoices(project_id=proj.id, client_busca=q, year=2099, month=6)
                    return {r.nf_number for r in rows}

                self.assertEqual(await numbers(nf), {nf})  # nº da NF
                self.assertEqual(await numbers(f"sao joao {tag}"), {nf})  # cliente, sem acento
                self.assertEqual(await numbers(f"FISCALIZACAO {nf}"), {nf})  # projeto + nº
                self.assertEqual(await numbers("medicao"), {nf})  # observações
                self.assertEqual(await numbers(f"{tag} inexistente"), set())  # toda palavra conta
                self.assertEqual(await numbers("100%"), set())  # curinga do LIKE é literal
            finally:
                await s.rollback()


if __name__ == "__main__":
    unittest.main()
