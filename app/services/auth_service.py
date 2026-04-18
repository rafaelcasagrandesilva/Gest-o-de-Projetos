from __future__ import annotations

import logging

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    PasswordHashingError,
    create_access_token,
    hash_password,
    verify_password_and_maybe_rehash,
)
from app.models.user import User

logger = logging.getLogger(__name__)
from app.repositories.users import UserRepository
from app.services.audit_service import AuditService


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = UserRepository(session)

    async def register(self, *, email: str, full_name: str, password: str) -> User:
        existing = await self.users.get_by_email(email)
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email já cadastrado.")
        try:
            password_hash = hash_password(password)
        except PasswordHashingError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível processar a senha neste momento.",
            ) from None
        user = User(email=email, full_name=full_name, password_hash=password_hash, is_active=True)
        await self.users.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def login(self, *, email: str, password: str, request: Request | None = None) -> str:
        user = await self.users.get_by_email(email)
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas.")
        ok, new_hash = verify_password_and_maybe_rehash(password, user.password_hash)
        if not ok:
            logger.warning(
                "Login recusado: senha incorreta ou hash não verificável (user_id=%s email=%s hash_prefix=%s)",
                user.id,
                user.email,
                (user.password_hash or "")[:16] + "…" if user.password_hash else "(vazio)",
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas.")
        if new_hash:
            user.password_hash = new_hash
            await self.session.commit()
            await self.session.refresh(user)
        await AuditService(self.session).log_action(
            user=user,
            action="login",
            entity="user",
            entity_id=user.id,
            before=None,
            after=None,
            context={"descricao": "Login bem-sucedido", "email": user.email},
            request=request,
            force_log=True,
        )
        await self.session.commit()
        return create_access_token(data={"sub": str(user.id)})

