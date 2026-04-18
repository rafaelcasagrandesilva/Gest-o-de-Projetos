#!/usr/bin/env python3
"""
Promove um usuário existente a ADMIN: tabela `user_roles` + preset completo em `user_permissions`.

Uso (na raiz do repositório, com venv ativo e DATABASE_URL no .env):

  python scripts/promote_user_admin.py
  python scripts/promote_user_admin.py --email outro@email.com

Ou: python manage.py promote_admin [--email ...]

Não altera regras de negócio; apenas ajusta vínculos desse usuário no banco.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def promote_user_to_admin(*, email: str) -> None:
    """Define role ADMIN, substitui `user_permissions` pelo preset ADMIN e remove vínculos em `project_users`."""
    from sqlalchemy import func, select

    from app.api.deps import ROLE_ADMIN
    from app.database.session import AsyncSessionLocal
    from app.models.user import User
    from app.services.users_service import UsersService

    email_norm = email.strip().lower()

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(User).where(func.lower(User.email) == email_norm))
        user = res.scalar_one_or_none()
        if not user:
            raise ValueError(f"Usuário não encontrado: {email!r}")

        svc = UsersService(session)
        await svc._apply_role_and_projects(
            user_id=user.id,
            role_name=ROLE_ADMIN,
            project_ids=[],
            apply_permission_preset=True,
        )
        await session.commit()
        logger.info(
            "OK: %s agora tem role ADMIN, permissões completas (preset) e vínculos de projeto limpos "
            "(ADMIN enxerga todos os projetos pelo RBAC).",
            email_norm,
        )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Promover usuário a ADMIN (RBAC + permissões).")
    parser.add_argument(
        "--email",
        default="admin@sgp.com",
        help="E-mail do usuário cadastrado (default: admin@sgp.com)",
    )
    args = parser.parse_args()
    try:
        await promote_user_to_admin(email=args.email)
    except ValueError as e:
        logger.error("%s", e)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
