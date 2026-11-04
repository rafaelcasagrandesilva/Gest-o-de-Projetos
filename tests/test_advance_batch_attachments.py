"""Documentos anexados à operação de antecipação.

Usa uma operação já existente no banco de testes (cópia de produção) dentro de uma transação
desfeita no fim; os arquivos vão para um diretório temporário.
"""

from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError


class AdvanceBatchAttachmentsDBTests(unittest.IsolatedAsyncioTestCase):
    async def test_ciclo_do_documento_da_operacao(self) -> None:
        from fastapi import HTTPException

        from app.core.config import settings
        from app.database.session import AsyncSessionLocal, engine
        from app.models.receivable_advance_batch import ReceivableAdvanceBatch
        from app.modules.receivables import router as rec
        from app.services.advance_batch_attachment_service import AdvanceBatchAttachmentService

        await engine.dispose()
        with TemporaryDirectory() as tmp:
            original_dir = settings.advance_batch_attachment_dir
            object.__setattr__(settings, "advance_batch_attachment_dir", tmp)
            try:
                async with AsyncSessionLocal() as s:
                    try:
                        await s.execute(text("SELECT 1 FROM receivable_advance_batch_attachments LIMIT 1"))
                    except ProgrammingError:
                        self.skipTest("Tabela ausente (rode alembic upgrade head).")
                    try:
                        batch = (await s.execute(select(ReceivableAdvanceBatch).limit(1))).scalar_one_or_none()
                        if batch is None:
                            self.skipTest("Banco de testes sem operações de antecipação.")
                        svc = AdvanceBatchAttachmentService(s)

                        # Lote com arquivo inválido: nada gravado (nem no disco).
                        with self.assertRaises(HTTPException):
                            await svc.save_many(
                                batch.id,
                                uploads=[("bordero.pdf", b"%PDF-1.4 ok", "application/pdf"), ("x.exe", b"MZ", None)],
                                uploaded_by_user_id=None,
                            )
                        self.assertEqual(await svc.list_for_batch(batch.id), [])

                        saved = await svc.save_many(
                            batch.id,
                            uploads=[("Borderô 13969.pdf", b"%PDF-1.4 bordero", "application/pdf")],
                            uploaded_by_user_id=None,
                        )
                        self.assertEqual(len(saved), 1)
                        path = svc.disk_path(await svc.get(batch.id, saved[0]["id"]))
                        self.assertTrue(path.is_file())

                        # Contagem na leitura da operação (lista e detalhe usam batch_read_dict).
                        from app.services.receivable_advance_batch_service import ReceivableAdvanceBatchService

                        full = await ReceivableAdvanceBatchService(s).get_batch(batch.id)
                        read = await ReceivableAdvanceBatchService(s).batch_read_dict(full)
                        self.assertEqual(read["attachment_count"], 1)

                        listed = await rec.list_advance_batch_attachments(batch.id, db=s)
                        self.assertEqual(listed[0].download_url, f"invoices/advance-batches/{batch.id}/attachments/{saved[0]['id']}/download")
                        resp = await rec.download_advance_batch_attachment(batch.id, saved[0]["id"], db=s)
                        self.assertEqual(resp.media_type, "application/pdf")
                        with self.assertRaises(HTTPException):
                            await rec.download_advance_batch_attachment(batch.id, uuid4(), db=s)

                        # Exclusão definitiva da operação limpa o disco (purge antes do CASCADE).
                        await svc.purge_for_batch(batch.id)
                        self.assertFalse(path.exists())
                        self.assertEqual(await svc.list_for_batch(batch.id), [])
                    finally:
                        await s.rollback()
            finally:
                object.__setattr__(settings, "advance_batch_attachment_dir", original_dir)
                await engine.dispose()


    async def test_exclusao_definitiva_apaga_os_documentos(self) -> None:
        from app.core.config import settings
        from app.database.session import AsyncSessionLocal, engine
        from app.models.receivable_advance_batch import ReceivableAdvanceBatch, ReceivableAdvanceBatchStatus
        from app.services.advance_batch_attachment_service import AdvanceBatchAttachmentService
        from app.services.receivable_advance_batch_service import ReceivableAdvanceBatchService

        await engine.dispose()
        with TemporaryDirectory() as tmp:
            original_dir = settings.advance_batch_attachment_dir
            object.__setattr__(settings, "advance_batch_attachment_dir", tmp)
            try:
                async with AsyncSessionLocal() as s:
                    try:
                        await s.execute(text("SELECT 1 FROM receivable_advance_batch_attachments LIMIT 1"))
                    except ProgrammingError:
                        self.skipTest("Tabela ausente (rode alembic upgrade head).")
                    try:
                        batch = (await s.execute(select(ReceivableAdvanceBatch).limit(1))).scalar_one_or_none()
                        if batch is None:
                            self.skipTest("Banco de testes sem operações de antecipação.")
                        files = AdvanceBatchAttachmentService(s)
                        saved = await files.save_many(
                            batch.id, uploads=[("termo.pdf", b"%PDF-1.4 termo", "application/pdf")], uploaded_by_user_id=None
                        )
                        path = files.disk_path(await files.get(batch.id, saved[0]["id"]))
                        # Só operação CANCELADA pode ser excluída (tudo desfeito no rollback).
                        batch.status = ReceivableAdvanceBatchStatus.CANCELLED
                        await s.flush()

                        await ReceivableAdvanceBatchService(s).delete_batch(batch_id=batch.id)
                        self.assertFalse(path.exists(), "arquivo ficou órfão no disco")
                        self.assertIsNone(await s.get(ReceivableAdvanceBatch, batch.id))
                    finally:
                        await s.rollback()
            finally:
                object.__setattr__(settings, "advance_batch_attachment_dir", original_dir)
                await engine.dispose()


if __name__ == "__main__":
    unittest.main()
