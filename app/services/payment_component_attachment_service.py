"""Comprovantes dos Componentes Variáveis de Pagamento (reembolso, ajuda de custo, …).

O anexo pertence ao COMPONENTE, nunca ao contexto: como o mesmo lançamento pode ter nascido
nos Custos do Projeto ou nos Custos Fixos, prender o arquivo ao componente faz um único
mecanismo servir as duas telas.

Disco, não banco: o arquivo vai para a raiz única de storage (ver `app/utils/storage.py`),
e o banco guarda só o caminho RELATIVO — o absoluto muda entre ambientes e a cada deploy.
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.payment_component import PaymentComponentAttachment

# Comprovante é PDF, foto de recibo ou o XML da nota. Allowlist explícita: qualquer coisa
# fora desta lista (executável, script, arquivo de macro) é recusada no upload.
ALLOWED_SUFFIXES = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".heic",
    ".heif",
    ".gif",
    ".xml",
}

# Teto por requisição: evita que um arrastar acidental de pasta inteira vire um upload
# gigante. Quem tem mais que isso envia em duas levas.
MAX_FILES_PER_UPLOAD = 20

_SAFE_NAME = re.compile(r"[^A-Za-z0-9À-ÿ ._-]")


def _clean_file_name(raw: str) -> str:
    """Nome exibido ao usuário: sem diretório e sem caractere de caminho."""
    name = Path(raw or "").name.strip() or "comprovante"
    return _SAFE_NAME.sub("_", name)[:255]


class PaymentComponentAttachmentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------ disco

    def base_dir(self) -> Path:
        return Path(settings.payment_component_attachment_dir)

    def disk_path(self, row: PaymentComponentAttachment) -> Path:
        return (self.base_dir() / row.stored_path).resolve()

    # ------------------------------------------------------------------ leitura

    def to_read_row(self, row: PaymentComponentAttachment) -> dict:
        return {
            "id": row.id,
            "component_id": row.component_id,
            "file_name": row.file_name,
            "mime_type": row.mime_type,
            "size_bytes": int(row.size_bytes or 0),
            "created_at": row.created_at,
            "download_url": f"payment-variable-components/{row.component_id}/attachments/{row.id}/download",
        }

    async def list_for_component(self, component_id: UUID) -> list[dict]:
        rows = (
            await self.db.execute(
                select(PaymentComponentAttachment)
                .where(PaymentComponentAttachment.component_id == component_id)
                .order_by(PaymentComponentAttachment.created_at.asc())
            )
        ).scalars().all()
        return [self.to_read_row(r) for r in rows]

    async def count_by_component(self, component_ids: list[UUID]) -> dict[UUID, int]:
        """Contagem por lançamento — uma query para a lista inteira (sem N+1 na tela)."""
        if not component_ids:
            return {}
        rows = (
            await self.db.execute(
                select(
                    PaymentComponentAttachment.component_id,
                    func.count(PaymentComponentAttachment.id),
                )
                .where(PaymentComponentAttachment.component_id.in_(component_ids))
                .group_by(PaymentComponentAttachment.component_id)
            )
        ).all()
        return {cid: int(total) for cid, total in rows}

    async def get(self, component_id: UUID, attachment_id: UUID) -> PaymentComponentAttachment | None:
        return (
            await self.db.execute(
                select(PaymentComponentAttachment).where(
                    PaymentComponentAttachment.id == attachment_id,
                    PaymentComponentAttachment.component_id == component_id,
                )
            )
        ).scalars().first()

    # ------------------------------------------------------------------ escrita

    @staticmethod
    def _validate(clean_name: str, body: bytes) -> None:
        """Recusa antes de gravar qualquer coisa (ver `save_many`)."""
        if Path(clean_name).suffix.lower() not in ALLOWED_SUFFIXES:
            raise HTTPException(
                status_code=400,
                detail=f"{clean_name}: formato não aceito. Envie PDF, imagem (JPG/PNG/WEBP/HEIC) "
                "ou XML da nota.",
            )
        limit = settings.payment_component_attachment_max_bytes
        if len(body) > limit:
            raise HTTPException(
                status_code=413,
                detail=f"{clean_name}: excede o limite de {limit // (1024 * 1024)} MB.",
            )
        if not body:
            raise HTTPException(status_code=400, detail=f"{clean_name}: arquivo vazio.")

    async def save_many(
        self,
        component_id: UUID,
        *,
        uploads: list[tuple[str, bytes, str | None]],
        uploaded_by_user_id: UUID | None,
    ) -> list[dict]:
        """Grava um LOTE de comprovantes — tudo ou nada.

        Valida todos ANTES de tocar o disco e, se ainda assim uma gravação falhar, apaga o
        que já tinha escrito: um arquivo recusado no meio do lote não pode deixar arquivo
        órfão no volume (o rollback do banco só desfaria os registros).
        """
        if not uploads:
            raise HTTPException(status_code=400, detail="Nenhum arquivo enviado.")
        if len(uploads) > MAX_FILES_PER_UPLOAD:
            raise HTTPException(
                status_code=400,
                detail=f"Envie no máximo {MAX_FILES_PER_UPLOAD} arquivos por vez.",
            )
        prepared = [(_clean_file_name(name), body, mime) for name, body, mime in uploads]
        for clean, body, _ in prepared:
            self._validate(clean, body)

        written: list[Path] = []
        try:
            out = []
            for clean, body, mime in prepared:
                row = await self._write(
                    component_id,
                    clean_name=clean,
                    body=body,
                    mime_type=mime,
                    uploaded_by_user_id=uploaded_by_user_id,
                )
                written.append(self.disk_path(row))
                out.append(self.to_read_row(row))
            return out
        except Exception:
            for path in written:
                path.unlink(missing_ok=True)
            raise

    async def save(
        self,
        component_id: UUID,
        *,
        file_name: str,
        body: bytes,
        mime_type: str | None,
        uploaded_by_user_id: UUID | None,
    ) -> dict:
        """Grava UM comprovante (atalho de `save_many` para uso direto/testes)."""
        clean = _clean_file_name(file_name)
        self._validate(clean, body)
        row = await self._write(
            component_id,
            clean_name=clean,
            body=body,
            mime_type=mime_type,
            uploaded_by_user_id=uploaded_by_user_id,
        )
        return self.to_read_row(row)

    async def _write(
        self,
        component_id: UUID,
        *,
        clean_name: str,
        body: bytes,
        mime_type: str | None,
        uploaded_by_user_id: UUID | None,
    ) -> PaymentComponentAttachment:
        suffix = Path(clean_name).suffix.lower()
        file_id = uuid4()
        base = self.base_dir() / str(component_id)
        base.mkdir(parents=True, exist_ok=True)
        dest = (base / f"{file_id}{suffix}").resolve()
        dest.write_bytes(body)

        row = PaymentComponentAttachment(
            id=file_id,
            component_id=component_id,
            file_name=clean_name,
            stored_path=str(dest.relative_to(self.base_dir().resolve())),
            mime_type=(mime_type or None),
            size_bytes=len(body),
            uploaded_by_user_id=uploaded_by_user_id,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def delete(self, component_id: UUID, attachment_id: UUID) -> bool:
        row = await self.get(component_id, attachment_id)
        if row is None:
            return False
        path = self.disk_path(row)
        await self.db.delete(row)
        await self.db.flush()
        path.unlink(missing_ok=True)
        return True

    async def purge_for_component(self, component_id: UUID) -> None:
        """Apaga arquivos + registros dos anexos do lançamento.

        Chamado ANTES de excluir o componente: o CASCADE do banco limparia só as linhas e
        deixaria os arquivos ocupando o volume para sempre.
        """
        rows = (
            await self.db.execute(
                select(PaymentComponentAttachment).where(
                    PaymentComponentAttachment.component_id == component_id
                )
            )
        ).scalars().all()
        if not rows:
            return
        paths = [self.disk_path(r) for r in rows]
        await self.db.execute(
            delete(PaymentComponentAttachment).where(
                PaymentComponentAttachment.component_id == component_id
            )
        )
        await self.db.flush()
        for path in paths:
            path.unlink(missing_ok=True)
        folder = (self.base_dir() / str(component_id)).resolve()
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
