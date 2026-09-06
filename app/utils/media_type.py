"""Tipo de mídia de um anexo na hora de servi-lo.

Anexos são gravados com o `Content-Type` que o navegador enviou no upload — que às vezes
vem vazio ou como o genérico `application/octet-stream` (celular, drag-and-drop de alguns
sistemas, importações antigas). Servido assim, o navegador BAIXA o arquivo em vez de
exibi-lo, e o botão "Ver" das telas não funciona. Aqui o nome original do arquivo desempata.
"""

from __future__ import annotations

import mimetypes

FALLBACK = "application/octet-stream"

# O `mimetypes` do sistema não conhece formatos recentes de foto — comprovante fotografado
# no iPhone cai exatamente aqui.
_EXTRA_TYPES = {
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".webp": "image/webp",
}


def resolve_media_type(stored_mime: str | None, file_name: str | None) -> str:
    """Mime para servir o arquivo: o gravado quando é específico, senão pela extensão."""
    mime = (stored_mime or "").strip().lower()
    if mime and mime != FALLBACK:
        return mime
    name = (file_name or "").lower()
    for ext, guessed in _EXTRA_TYPES.items():
        if name.endswith(ext):
            return guessed
    return mimetypes.guess_type(name)[0] or FALLBACK
