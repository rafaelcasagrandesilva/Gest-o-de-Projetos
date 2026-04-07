from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.schemas.auth import LoginRequest, RegisterRequest, Token
from app.schemas.users import UserRead
from app.services.auth_service import AuthService


router = APIRouter()


@router.post("/register", response_model=UserRead)
@router.post("/register/", response_model=UserRead)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> UserRead:
    user = await AuthService(db).register(email=payload.email, full_name=payload.full_name, password=payload.password)
    return UserRead.model_validate({**user.__dict__, "role_names": []})


@router.post("/login", response_model=Token)
@router.post("/login/", response_model=Token)
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)) -> Token:
    token = await AuthService(db).login(email=payload.email, password=payload.password, request=request)
    return Token(access_token=token)

