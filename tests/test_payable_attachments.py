"""Comprovantes no Contas a Pagar: o título de Premiação/Reembolso mostra os anexos do componente.

O título (origin=VARIABLE) aponta para o componente de origem pelo `ref_id`. O CAP lista e baixa
os comprovantes pelas rotas dele (permissão do próprio CAP), e a lista traz a contagem por título.

Roda numa transação desfeita no fim; arquivos vão para um diretório temporário.
"""

from __future__ import annotations

import unittest
from datetime import date
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError


class PayableAttachmentsDBTests(unittest.IsolatedAsyncioTestCase):
    async def test_titulo_do_reembolso_lista_e_baixa_o_comprovante(self) -> None:
        from fastapi import HTTPException

        from app.core.config import settings
        from app.database.session import AsyncSessionLocal, engine
        from app.models.company_finance import CompanyFinancialItem
        from app.models.employee import Employee
        from app.models.payable_snapshot import PayableOrigin, PayableSnapshot
        from app.models.payment_component import PaymentComponentType
        from app.modules.financial import router as fin
        from app.services.payable_snapshot_service import PayableSnapshotService
        from app.services.payment_component_attachment_service import PaymentComponentAttachmentService
        from app.services.payment_variable_component_service import PaymentVariableComponentService

        await engine.dispose()
        tag = uuid4().hex[:6]
        comp_month = date(2099, 5, 1)

        with TemporaryDirectory() as tmp:
            original_dir = settings.payment_component_attachment_dir
            object.__setattr__(settings, "payment_component_attachment_dir", tmp)
            try:
                async with AsyncSessionLocal() as s:
                    try:
                        await s.execute(text("SELECT 1 FROM payment_component_attachments LIMIT 1"))
                    except ProgrammingError:
                        self.skipTest("Tabelas ausentes (rode alembic upgrade head).")
                    try:
                        reembolso = (
                            await s.execute(select(PaymentComponentType).where(PaymentComponentType.code == "reembolso"))
                        ).scalars().first()
                        self.assertIsNotNone(reembolso, "seed do tipo 'reembolso' ausente")

                        emp = Employee(
                            full_name=f"Socio {tag}", email=f"socio_{tag}@ex.com", employment_type="PJ",
                            is_active=True, salary_base=0.0, total_cost=0,
                        )
                        s.add(emp)
                        await s.flush()
                        item = CompanyFinancialItem(
                            tipo="custo_fixo", nome=emp.full_name, valor_referencia=1000.0,
                            is_active=True, start_date=date(2099, 1, 1), employee_id=emp.id,
                            cost_center="Administrativo", cost_center_system="ADMINISTRATIVO",
                        )
                        s.add(item)
                        await s.flush()

                        comp = await PaymentVariableComponentService(s).create(
                            {
                                "type_id": reembolso.id, "amount": 321.13, "note": "Material de escritório",
                                "company_financial_item_id": item.id, "competencia": comp_month,
                            }
                        )
                        files = PaymentComponentAttachmentService(s)
                        att = await files.save(
                            comp["id"], file_name="nota.pdf", body=b"%PDF-1.4 recibo",
                            mime_type="application/pdf", uploaded_by_user_id=None,
                        )
                        titulo = (
                            await s.execute(
                                select(PayableSnapshot).where(
                                    PayableSnapshot.origin == PayableOrigin.VARIABLE.value,
                                    PayableSnapshot.ref_id == comp["id"],
                                )
                            )
                        ).scalar_one()

                        # Lista do CAP: contagem por título; título sem componente fica em 0.
                        svc = PayableSnapshotService(s)
                        outro = (
                            await s.execute(select(PayableSnapshot).where(PayableSnapshot.id != titulo.id).limit(1))
                        ).scalar_one_or_none()
                        rows = [titulo] + ([outro] if outro is not None else [])
                        reads = await fin._snapshots_to_read(svc, rows)
                        self.assertEqual(reads[0].attachment_count, 1)
                        if outro is not None and outro.origin != PayableOrigin.VARIABLE.value:
                            self.assertEqual(reads[1].attachment_count, 0)

                        with patch.object(fin, "user_sees_all_projects", return_value=True), patch.object(fin, "sensitive_include", return_value=True):
                            listed = await fin.list_payable_attachments(titulo.id, db=s, user=object())
                            self.assertEqual([a.file_name for a in listed], ["nota.pdf"])
                            self.assertEqual(
                                listed[0].download_url,
                                f"financial/payables/{titulo.id}/attachments/{att['id']}/download",
                            )
                            resp = await fin.download_payable_attachment(titulo.id, att["id"], db=s, user=object())
                            self.assertEqual(resp.media_type, "application/pdf")

                            # Anexo de OUTRO componente não sai por este título.
                            with self.assertRaises(HTTPException) as ctx:
                                await fin.download_payable_attachment(titulo.id, uuid4(), db=s, user=object())
                            self.assertEqual(ctx.exception.status_code, 404)

                            # Título que não é Premiação/Reembolso: lista vazia, sem erro.
                            if outro is not None and outro.origin != PayableOrigin.VARIABLE.value:
                                self.assertEqual(await fin.list_payable_attachments(outro.id, db=s, user=object()), [])
                    finally:
                        await s.rollback()
            finally:
                object.__setattr__(settings, "payment_component_attachment_dir", original_dir)
                await engine.dispose()


if __name__ == "__main__":
    unittest.main()
