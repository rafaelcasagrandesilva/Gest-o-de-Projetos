#!/usr/bin/env python3
"""
CLI de manutenção do SGP.

Uso:
  python manage.py reset_db              # pede confirmação (digite o nome do banco)
  python manage.py reset_db --yes        # sem prompt (CI / automação)
  python manage.py promote_admin         # promove usuário a ADMIN (RBAC + permissões)
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

    p_promote = sub.add_parser("promote_admin", help="Atribui role ADMIN + permissões completas a um usuário")
    p_promote.add_argument(
        "--email",
        default="admin@sgp.com",
        help="E-mail do usuário (default: admin@sgp.com)",
    )

    p_legal = sub.add_parser(
        "seed_legal",
        help="Carga do Workspace Jurídico para desenvolvimento (idempotente). "
        "Em produção a carga oficial é a importação da planilha pela tela.",
    )
    p_legal.add_argument(
        "--file",
        default=None,
        help="JSON de seed local, não versionado (default: app/scripts/data/legal_seed.json)",
    )
    p_legal.add_argument("--xlsx", default=None, help="Importar direto da planilha (.xlsx)")
    p_legal.add_argument("--painel", default=None, help="painel_passivo.html (opcional)")

    args = parser.parse_args()
    _configure_logging()

    if args.command == "reset_db":
        import asyncio

        from app.db_maintenance.reset import run_full_reset

        asyncio.run(run_full_reset(skip_confirm=args.yes))
        logging.getLogger(__name__).info("reset_db concluído com sucesso.")
        return

    if args.command == "promote_admin":
        import asyncio

        from scripts.promote_user_admin import promote_user_to_admin

        try:
            asyncio.run(promote_user_to_admin(email=args.email))
        except ValueError as e:
            logging.getLogger(__name__).error("%s", e)
            sys.exit(1)
        logging.getLogger(__name__).info("promote_admin concluído.")
        return

    if args.command == "seed_legal":
        import asyncio
        from pathlib import Path as _Path

        from app.scripts.seed_legal import seed_legal

        from app.services.legal_import_parser import LegalImportSourceError

        try:
            report = asyncio.run(
                seed_legal(
                    _Path(args.file) if args.file else None,
                    xlsx=_Path(args.xlsx).expanduser() if args.xlsx else None,
                    panel=_Path(args.painel).expanduser() if args.painel else None,
                )
            )
        except (FileNotFoundError, LegalImportSourceError) as e:
            logging.getLogger(__name__).error("%s", e)
            sys.exit(1)
        s = report.summary
        logging.getLogger(__name__).info(
            "seed_legal concluído: pessoas criadas=%d atualizadas=%d · processos criados=%d "
            "atualizados=%d · sem alteração=%d",
            s.people_new,
            s.people_updated,
            s.cases_new,
            s.cases_updated,
            s.people_unchanged + s.cases_unchanged,
        )
        return

    parser.error("Comando desconhecido.")


if __name__ == "__main__":
    main()
