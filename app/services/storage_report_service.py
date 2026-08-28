"""Confronta os anexos registrados no banco com os arquivos em disco.

Serve para responder "o que preciso reenviar?" depois de um redeploy que apagou
uploads gravados fora do volume persistente (contexto em `app/utils/storage.py`).

Cada tipo de anexo é resolvido com a MESMA regra do endpoint de download
correspondente, para o relatório refletir exatamente o que o usuário veria ao
clicar em Download.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings


@dataclass(frozen=True)
class AttachmentFile:
    tipo: str
    onde: str  # projeto / ativo / NF a que o arquivo pertence
    titulo: str
    arquivo: str  # nome original, o que o usuário reconhece na tela
    enviado_em: str
    caminho: str
    existe: bool

    def as_dict(self) -> dict:
        return asdict(self)


# (rótulo) -> (diretório base, SQL). Todas as consultas devolvem as mesmas colunas.
_SOURCES: dict[str, tuple[str, str]] = {
    "Documento de projeto": (
        "project_document_dir",
        """
        SELECT p.name AS onde, d.title AS titulo, d.original_filename AS arquivo,
               d.storage_path AS caminho, d.uploaded_at AS enviado_em
          FROM project_documents d
          JOIN projects p ON p.id = d.project_id
         WHERE COALESCE(d.is_active, TRUE)
         ORDER BY d.uploaded_at
        """,
    ),
    "Anexo de ativo": (
        "asset_upload_dir",
        """
        SELECT a.asset_code || ' — ' || a.name AS onde, at.file_type::text AS titulo,
               at.file_name AS arquivo, at.stored_path AS caminho, at.created_at AS enviado_em
          FROM asset_attachments at
          JOIN assets a ON a.id = at.asset_id
         WHERE at.deleted_at IS NULL
         ORDER BY at.created_at
        """,
    ),
    "PDF de NF": (
        "receivable_upload_dir",
        """
        SELECT p.name || ' — NF ' || i.nf_number AS onde, 'NF' AS titulo,
               f.file_name AS arquivo, f.stored_path AS caminho, f.created_at AS enviado_em
          FROM receivable_invoice_files f
          JOIN receivable_invoices i ON i.id = f.invoice_id
          JOIN projects p ON p.id = i.project_id
         ORDER BY f.created_at
        """,
    ),
}


async def collect_attachments(session: AsyncSession) -> list[AttachmentFile]:
    """Todos os anexos registrados, com a marca de existir ou não em disco."""
    achados: list[AttachmentFile] = []
    for tipo, (settings_field, sql) in _SOURCES.items():
        base = Path(getattr(settings, settings_field))
        for row in (await session.execute(text(sql))).mappings():
            caminho = (base / row["caminho"]).resolve()
            achados.append(
                AttachmentFile(
                    tipo=tipo,
                    onde=row["onde"] or "—",
                    titulo=row["titulo"] or "—",
                    arquivo=row["arquivo"] or "—",
                    enviado_em=str(row["enviado_em"])[:19],
                    caminho=str(caminho),
                    existe=caminho.is_file(),
                )
            )
    return achados


async def missing_files_report(session: AsyncSession) -> dict:
    """Resumo por tipo + lista dos ausentes, pronto para JSON ou impressão."""
    achados = await collect_attachments(session)
    resumo = []
    for tipo in _SOURCES:
        do_tipo = [a for a in achados if a.tipo == tipo]
        resumo.append(
            {
                "tipo": tipo,
                "total": len(do_tipo),
                "ausentes": sum(1 for a in do_tipo if not a.existe),
            }
        )
    return {
        "diretorios": {nome: str(p.resolve()) for nome, p in settings.storage_dirs().items()},
        "raiz": str(settings.resolved_storage_root() or ""),
        "resumo": resumo,
        "total_ausentes": sum(1 for a in achados if not a.existe),
        "total_registros": len(achados),
        "ausentes": [a.as_dict() for a in achados if not a.existe],
    }
