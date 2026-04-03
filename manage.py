#!/usr/bin/env python3
"""
CLI de manutenção do SGP.

Uso:
  python manage.py reset_db              # pede confirmação (digite o nome do banco)
  python manage.py reset_db --yes        # sem prompt (CI / automação)
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Raiz do repo no path para `import app`
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s [%(name)s] %(message)s",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="SGP — utilitários de banco")
    sub = parser.add_subparsers(dest="command", required=True)

    p_reset = sub.add_parser("reset_db", help="Drop + create DB, alembic upgrade head, validação, seed admin")
    p_reset.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Não pedir confirmação interativa (use com cuidado).",
    )

    args = parser.parse_args()
    _configure_logging()

    if args.command == "reset_db":
        import asyncio

        from app.db_maintenance.reset import run_full_reset

        asyncio.run(run_full_reset(skip_confirm=args.yes))
        logging.getLogger(__name__).info("reset_db concluído com sucesso.")
        return

    parser.error("Comando desconhecido.")


if __name__ == "__main__":
    main()
