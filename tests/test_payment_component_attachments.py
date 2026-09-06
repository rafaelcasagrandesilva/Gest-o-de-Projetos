"""Comprovantes dos Componentes Variáveis de Pagamento (anexo do reembolso).

Cobre o que não pode quebrar: o arquivo grava sob a raiz de storage, a contagem que a tela
exibe bate com o disco, o formato/tamanho recusados não deixam lixo e — o ponto mais fácil
de esquecer — excluir o lançamento apaga TAMBÉM os arquivos, não só as linhas do banco.
"""

from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError


class PaymentComponentAttachmentDBTests(unittest.IsolatedAsyncioTestCase):
    async def test_attachment_lifecycle(self) -> None:
        from app.core.config import settings
        from app.database.session import AsyncSessionLocal, engine
        from app.models.employee import Employee
        from app.models.payment_component import PaymentComponentType
        from app.models.project import Project
        from app.models.project_operational import ProjectLabor
        from app.services.payment_component_attachment_service import (
            PaymentComponentAttachmentService,
        )
        from app.services.payment_variable_component_service import PaymentVariableComponentService

        await engine.dispose()
        tag = uuid4().hex[:6]
        worked = date(2099, 5, 1)

        with TemporaryDirectory() as tmp:
            original_dir = settings.payment_component_attachment_dir
            object.__setattr__(settings, "payment_component_attachment_dir", tmp)
            try:
                async with AsyncSessionLocal() as s:
                    try:
                        await s.execute(text("SELECT 1 FROM payment_component_attachments LIMIT 1"))
                    except ProgrammingError:
                        self.skipTest("Tabelas ausentes (rode alembic upgrade head).")

                    reembolso = (
                        await s.execute(
                            select(PaymentComponentType).where(PaymentComponentType.code == "reembolso")
                        )
                    ).scalars().first()
                    self.assertIsNotNone(reembolso, "seed do tipo 'reembolso' ausente")

                    emp = Employee(
                        full_name=f"PCA {tag}", email=f"pca_{tag}@ex.com", employment_type="PJ",
                        is_active=True, salary_base=5000.0, total_cost=0,
                    )
                    proj = Project(name=f"Proj PCA {tag}", is_active=True)
                    s.add_all([emp, proj])
                    await s.flush()
                    labor = ProjectLabor(
                        project_id=proj.id, employee_id=emp.id, competencia=worked,
                        scenario="REALIZADO", allocation_percentage=50.0,
                    )
                    s.add(labor)
                    await s.flush()

                    svc = PaymentVariableComponentService(s)
                    files = PaymentComponentAttachmentService(s)

                    comp = await svc.create(
                        {"type_id": reembolso.id, "amount": 250.0, "project_labor_id": labor.id}
                    )
                    self.assertEqual(comp["attachment_count"], 0, "lançamento novo nasce sem anexo")

                    # --- Upload: arquivo em disco + metadados no banco ---
                    a1 = await files.save(
                        comp["id"], file_name="nota fiscal.pdf", body=b"%PDF-1.4 recibo",
                        mime_type="application/pdf", uploaded_by_user_id=None,
                    )
                    a2 = await files.save(
                        comp["id"], file_name="cupom.jpg", body=b"\xff\xd8\xff foto",
                        mime_type="image/jpeg", uploaded_by_user_id=None,
                    )
                    paths = [
                        files.disk_path(await files.get(comp["id"], a["id"])) for a in (a1, a2)
                    ]
                    for path in paths:
                        self.assertTrue(path.is_file(), f"arquivo não gravado: {path}")
                    self.assertTrue(
                        str(paths[0]).startswith(str(Path(tmp).resolve())),
                        "arquivo gravado fora da raiz de storage",
                    )

                    # --- Contagem: é o número que a tela mostra no clipe ---
                    self.assertEqual(
                        (await files.count_by_component([comp["id"]]))[comp["id"]], 2
                    )
                    listado = await svc.list_for_project_labor(labor.id)
                    self.assertEqual([r["attachment_count"] for r in listado], [2])

                    # --- Formato fora da allowlist é recusado, sem gravar nada ---
                    with self.assertRaises(Exception):
                        await files.save(
                            comp["id"], file_name="malware.exe", body=b"MZ",
                            mime_type="application/octet-stream", uploaded_by_user_id=None,
                        )
                    # --- Acima do limite também ---
                    with self.assertRaises(Exception):
                        await files.save(
                            comp["id"],
                            file_name="grande.pdf",
                            body=b"x" * (settings.payment_component_attachment_max_bytes + 1),
                            mime_type="application/pdf",
                            uploaded_by_user_id=None,
                        )
                    self.assertEqual(
                        (await files.count_by_component([comp["id"]]))[comp["id"]], 2,
                        "recusa não pode alterar o que já estava anexado",
                    )

                    # --- Lote com um arquivo inválido não grava NENHUM (nem no disco) ---
                    antes = set(Path(tmp).rglob("*.*"))
                    with self.assertRaises(Exception):
                        await files.save_many(
                            comp["id"],
                            uploads=[
                                ("ok.pdf", b"%PDF-1.4 valido", "application/pdf"),
                                ("script.sh", b"rm -rf /", "text/x-sh"),
                            ],
                            uploaded_by_user_id=None,
                        )
                    self.assertEqual(
                        set(Path(tmp).rglob("*.*")), antes, "lote recusado deixou arquivo no disco"
                    )
                    self.assertEqual(
                        (await files.count_by_component([comp["id"]]))[comp["id"]], 2
                    )

                    # --- Excluir um anexo tira o arquivo do disco ---
                    self.assertTrue(await files.delete(comp["id"], a2["id"]))
                    self.assertFalse(paths[1].exists())
                    self.assertTrue(paths[0].is_file())

                    # --- Excluir o LANÇAMENTO leva os arquivos junto (não só as linhas) ---
                    await svc.delete(comp["id"])
                    self.assertFalse(paths[0].exists(), "arquivo órfão deixado no volume")
                    self.assertEqual(await files.count_by_component([comp["id"]]), {})

                    # Limpeza dos dados de teste.
                    await s.execute(
                        text("DELETE FROM project_labors WHERE id = :i"), {"i": str(labor.id)}
                    )
                    for obj in (emp, proj):
                        fresh = await s.get(type(obj), obj.id)
                        if fresh is not None:
                            await s.delete(fresh)
                    await s.commit()
            finally:
                object.__setattr__(settings, "payment_component_attachment_dir", original_dir)


if __name__ == "__main__":
    unittest.main()
