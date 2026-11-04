"""Documentos anexados à operação de antecipação (borderô/termo da instituição).

Mesmo mecanismo dos comprovantes de pagamento variável (`payment_component_attachment_service`):
arquivo em disco sob a raiz única de storage, banco com o caminho RELATIVO, lote tudo-ou-nada,
mesma allowlist de formatos e mesma limpeza de nome. Muda só o dono (a operação) e o limite.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.receivable_advance_batch import ReceivableAdvanceBatchAttachment
from app.services.payment_component_attachment_service import (
    ALLOWED_SUFFIXES,
    MAX_FILES_PER_UPLOAD,
    _clean_file_name,
)


class AdvanceBatchAttachmentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------ disco

    def base_dir(self) -> Path:
        return Path(settings.advance_batch_attachment_dir)

    def disk_path(self, row: ReceivableAdvanceBatchAttachment) -> Path:
        return (self.base_dir() / row.stored_path).resolve()

    # ------------------------------------------------------------------ leitura

    @staticmethod
    def to_read_row(row: ReceivableAdvanceBatchAttachment) -> dict:
        return {
            "id": row.id,
            "batch_id": row.batch_id,
            "file_name": row.file_name,
            "mime_type": row.mime_type,
            "size_bytes": int(row.size_bytes or 0),
            "created_at": row.created_at,
            "download_url": f"invoices/advance-batches/{row.batch_id}/attachments/{row.id}/download",
        }

    async def list_for_batch(self, batch_id: UUID) -> list[dict]:
        rows = (
            await self.db.execute(
                select(ReceivableAdvanceBatchAttachment)
                .where(ReceivableAdvanceBatchAttachment.batch_id == batch_id)
                .order_by(ReceivableAdvanceBatchAttachment.created_at.asc())
            )
        ).scalars().all()
        return [self.to_read_row(r) for r in rows]

    async def count_by_batch(self, batch_ids: list[UUID]) -> dict[UUID, int]:
        """Contagem por operação — uma query para a lista inteira (sem N+1)."""
        if not batch_ids:
            return {}
        rows = (
            await self.db.execute(
                select(ReceivableAdvanceBatchAttachment.batch_id, func.count(ReceivableAdvanceBatchAttachment.id))
                .where(ReceivableAdvanceBatchAttachment.batch_id.in_(batch_ids))
                .group_by(ReceivableAdvanceBatchAttachment.batch_id)
            )
        ).all()
        return {bid: int(total) for bid, total in rows}

    async def get(self, batch_id: UUID, attachment_id: UUID) -> ReceivableAdvanceBatchAttachment | None:
        return (
            await self.db.execute(
                select(ReceivableAdvanceBatchAttachment).where(
                    ReceivableAdvanceBatchAttachment.id == attachment_id,
                    ReceivableAdvanceBatchAttachment.batch_id == batch_id,
                )
            )
        ).scalars().first()

    # ------------------------------------------------------------------ escrita

    @staticmethod
    def _validate(clean_name: str, body: bytes) -> None:
        if Path(clean_name).suffix.lower() not in ALLOWED_SUFFIXES:
            raise HTTPException(
                status_code=400,
                detail=f"{clean_name}: formato não aceito. Envie PDF, imagem (JPG/PNG/WEBP/HEIC) ou XML.",
            )
        limit = settings.advance_batch_attachment_max_bytes
        if len(body) > limit:
            raise HTTPException(status_code=413, detail=f"{clean_name}: excede o limite de {limit // (1024 * 1024)} MB.")
        if not body:
            raise HTTPException(status_code=400, detail=f"{clean_name}: arquivo vazio.")

    async def save_many(
        self,
        batch_id: UUID,
        *,
        uploads: list[tuple[str, bytes, str | None]],
        uploaded_by_user_id: UUID | None,
    ) -> list[dict]:
        """Grava um LOTE — tudo ou nada (valida tudo antes; desfaz o disco se algo falhar)."""
        if not uploads:
            raise HTTPException(status_code=400, detail="Nenhum arquivo enviado.")
        if len(uploads) > MAX_FILES_PER_UPLOAD:
            raise HTTPException(status_code=400, detail=f"Envie no máximo {MAX_FILES_PER_UPLOAD} arquivos por vez.")
        prepared = [(_clean_file_name(name), body, mime) for name, body, mime in uploads]
        for clean, body, _ in prepared:
            self._validate(clean, body)

        written: list[Path] = []
        try:
            out = []
            for clean, body, mime in prepared:
                row = await self._write(
                    batch_id, clean_name=clean, body=body, mime_type=mime, uploaded_by_user_id=uploaded_by_user_id
                )
                written.append(self.disk_path(row))
                out.append(self.to_read_row(row))
            return out
        except Exception:
            for path in written:
                path.unlink(missing_ok=True)
            raise

    async def _write(
        self,
        batch_id: UUID,
        *,
        clean_name: str,
        body: bytes,
        mime_type: str | None,
        uploaded_by_user_id: UUID | None,
    ) -> ReceivableAdvanceBatchAttachment:
        suffix = Path(clean_name).suffix.lower()
        file_id = uuid4()
        base = self.base_dir() / str(batch_id)
        base.mkdir(parents=True, exist_ok=True)
        dest = (base / f"{file_id}{suffix}").resolve()
        dest.write_bytes(body)
        row = ReceivableAdvanceBatchAttachment(
            id=file_id,
            batch_id=batch_id,
            file_name=clean_name,
            stored_path=str(dest.relative_to(self.base_dir().resolve())),
            mime_type=(mime_type or None),
            size_bytes=len(body),
            uploaded_by_user_id=uploaded_by_user_id,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def delete(self, batch_id: UUID, attachment_id: UUID) -> bool:
        row = await self.get(batch_id, attachment_id)
        if row is None:
            return False
        path = self.disk_path(row)
        await self.db.delete(row)
        await self.db.flush()
        path.unlink(missing_ok=True)
        return True

    async def purge_for_batch(self, batch_id: UUID) -> None:
        """Apaga arquivos + registros ANTES de excluir a operação (o CASCADE só limparia as linhas)."""
        rows = (
            await self.db.execute(
                select(ReceivableAdvanceBatchAttachment).where(ReceivableAdvanceBatchAttachment.batch_id == batch_id)
            )
        ).scalars().all()
        paths = [self.disk_path(r) for r in rows]
        for r in rows:
            await self.db.delete(r)
        await self.db.flush()
        for path in paths:
            path.unlink(missing_ok=True)
