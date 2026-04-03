from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ROLE_ADMIN
from app.core.security import hash_password
from app.database.session import AsyncSessionLocal
from app.models.user import Role, User, UserRole

logger = logging.getLogger(__name__)


async def seed_admin() -> None:
    """
    Garante que exista pelo menos um usuário com a role de administrador.
    Alinha o nome da role com ROLE_ADMIN ("ADMIN") usado no RBAC.
    """
    async with AsyncSessionLocal() as session:
        await _seed_admin_session(session)


async def _seed_admin_session(session: AsyncSession) -> None:
    has_admin = await _any_user_has_admin_role(session)
    if has_admin:
        logger.info("Startup seed: já existe usuário com role %s — nada a fazer.", ROLE_ADMIN)
        return

    role = await _get_or_create_admin_role(session)
    user = await _get_or_create_default_admin_user(session)

    linked = await _user_has_admin_role_link(session, user.id, role.id)
    if not linked:
        session.add(UserRole(user_id=user.id, role_id=role.id))

    await session.commit()
    logger.info(
        "Startup seed: usuário admin garantido — email=%s (senha padrão se recém-criado: defina em produção).",
        "admin@admin.com",
    )


async def _any_user_has_admin_role(session: AsyncSession) -> bool:
    stmt = (
        select(User.id)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(Role.name == ROLE_ADMIN)
        .limit(1)
    )
    row = await session.execute(stmt)
    return row.scalar_one_or_none() is not None


async def _get_or_create_admin_role(session: AsyncSession) -> Role:
    res = await session.execute(select(Role).where(Role.name == ROLE_ADMIN))
    role = res.scalar_one_or_none()
    if role is None:
        role = Role(name=ROLE_ADMIN, description="Administrator")
        session.add(role)
        await session.flush()
    return role


async def _get_or_create_default_admin_user(session: AsyncSession) -> User:
    res = await session.execute(select(User).where(User.email == "admin@admin.com"))
    user = res.scalar_one_or_none()
    if user is None:
        user = User(
            email="admin@admin.com",
            full_name="Admin",
            password_hash=hash_password("123456"),
            is_active=True,
        )
        session.add(user)
        await session.flush()
    return user


async def _user_has_admin_role_link(session: AsyncSession, user_id, role_id) -> bool:
    stmt = select(UserRole.id).where(UserRole.user_id == user_id, UserRole.role_id == role_id).limit(1)
    row = await session.execute(stmt)
    return row.scalar_one_or_none() is not None
