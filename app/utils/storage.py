"""Diagnóstico e resgate dos diretórios de upload em disco.

Todo arquivo enviado pelo sistema (PDFs de NF, anexos de ativos, documentos de
projeto) mora em disco. Em produção apenas o diretório das NFs apontava para o
volume persistente; os demais ficavam no default relativo, dentro do container
efêmero, e desapareciam a cada redeploy — o registro continuava no banco e o
download devolvia 404.

Com a raiz única (`Settings.resolved_storage_root`) os diretórios passam a nascer
no volume. Este módulo cobre as duas pontas restantes:

* `log_storage_dirs` — deixa explícito no log de startup onde cada tipo de arquivo
  está sendo gravado, e alerta em produção quando o caminho é relativo (efêmero).
* `salvage_legacy_uploads` — copia, uma única vez, o que ainda restou no diretório
  legado para a raiz nova, evitando perder o que foi enviado desde o último deploy.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

# Defaults históricos (relativos ao CWD do processo) de onde pode ter sobrado arquivo.
LEGACY_DIRS: dict[str, str] = {
    "RECEIVABLE_UPLOAD_DIR": "var/receivable_uploads",
    "ASSET_UPLOAD_DIR": "var/asset_uploads",
    "PROJECT_DOCUMENT_DIR": "var/project_documents",
}


def log_storage_dirs() -> None:
    """Registra os diretórios de upload em uso e alerta sobre disco efêmero."""
    root = settings.resolved_storage_root()
    logger.info("Storage: raiz = %s", root if root is not None else "(defaults relativos)")
    for name, path in settings.storage_dirs().items():
        logger.info("Storage: %s = %s", name, path.resolve())
        if settings.is_production() and not path.is_absolute():
            logger.warning(
                "Storage: %s usa caminho relativo (%s) — em produção os arquivos se perdem "
                "no próximo redeploy. Defina STORAGE_ROOT com o mount do volume persistente.",
                name,
                path,
            )


def salvage_legacy_uploads() -> dict[str, int]:
    """Copia arquivos remanescentes dos diretórios legados para os atuais.

    Idempotente: só copia o que ainda não existe no destino e nunca apaga a origem.
    Retorna a contagem de arquivos copiados por diretório (vazio quando nada a fazer).
    """
    copied: dict[str, int] = {}
    for name, legacy_raw in LEGACY_DIRS.items():
        legacy = Path(legacy_raw).resolve()
        current = settings.storage_dirs()[name].resolve()
        if legacy == current or not legacy.is_dir():
            continue
        count = 0
        for src in legacy.rglob("*"):
            if not src.is_file():
                continue
            dest = current / src.relative_to(legacy)
            if dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            count += 1
        if count:
            copied[name] = count
            logger.warning(
                "Storage: %d arquivo(s) copiado(s) de %s (legado/efêmero) para %s.",
                count,
                legacy,
                current,
            )
    return copied
