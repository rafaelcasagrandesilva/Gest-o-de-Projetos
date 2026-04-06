"""Executa `alembic upgrade head` no startup (Railway / deploy sem release command)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _project_root() -> Path:
    # app/core/run_migrations.py -> parents[2] = raiz do repositório
    return Path(__file__).resolve().parents[2]


def run_alembic_upgrade() -> None:
    """
    Aplica migrations pendentes (cria permissions / user_permissions, seeds, etc.).
    Idempotente: se já estiver em head, retorna rápido.
    """
    root = _project_root()
    alembic_ini = root / "alembic.ini"
    if not alembic_ini.is_file():
        logger.warning("alembic.ini não encontrado em %s — pulando migrations.", root)
        return

    env = os.environ.copy()
    # Garante imports `app.*` ao rodar alembic como subprocess
    py_path = env.get("PYTHONPATH", "")
    sep = os.pathsep
    if str(root) not in py_path.split(sep):
        env["PYTHONPATH"] = f"{root}{sep}{py_path}" if py_path else str(root)

    try:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(root),
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("Alembic: upgrade head concluído.")
    except subprocess.CalledProcessError as e:
        logger.error(
            "Alembic upgrade head falhou (stdout=%r stderr=%r)",
            e.stdout,
            e.stderr,
        )
        raise RuntimeError("Falha ao aplicar migrations Alembic. Verifique DATABASE_URL e logs.") from e
