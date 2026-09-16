from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.permission_codes import USERS_MANAGE
from app.database.session import get_db
from app.schemas.auth import LoginRequest, RegisterRequest, Token
from app.schemas.users import UserRead
from app.services.auth_service import AuthService


router = APIRouter()


# Criar conta NÃO é público: antes qualquer um sem login criava usuário por aqui. Fica restrito a quem
# administra usuários (a tela de Usuários usa /users; nada no frontend chama esta rota).
_register_guard = [Depends(require_permission(USERS_MANAGE))]


@router.post("/register", response_model=UserRead, dependencies=_register_guard)
@router.post("/register/", response_model=UserRead, dependencies=_register_guard)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> UserRead:
    user = await AuthService(db).register(email=payload.email, full_name=payload.full_name, password=payload.password)
    return UserRead.model_validate({**user.__dict__, "role_names": []})


@router.post("/login", response_model=Token)
@router.post("/login/", response_model=Token)
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)) -> Token:
    token = await AuthService(db).login(email=payload.email, password=payload.password, request=request)
    return Token(access_token=token)

