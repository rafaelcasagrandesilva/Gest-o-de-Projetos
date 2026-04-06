from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import UUIDTimestampRead


class RoleRead(UUIDTimestampRead):
    name: str
    description: str | None = None


class UserRead(UUIDTimestampRead):
    email: EmailStr
    full_name: str
    is_active: bool
    role_names: list[str] = []
    project_ids: list[UUID] = []
    permission_names: list[str] = []


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=6, max_length=128)
    is_active: bool = True
    role_name: str = Field(default="CONSULTA", min_length=3, max_length=50)
    project_ids: list[UUID] | None = None


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    password: str | None = Field(default=None, min_length=6, max_length=128)
    is_active: bool | None = None
    role_name: str | None = Field(default=None, min_length=3, max_length=50)
    project_ids: list[UUID] | None = None
    permission_names: list[str] | None = None


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    description: str | None = Field(default=None, max_length=255)


class AssignRoleRequest(BaseModel):
    role_name: str = Field(min_length=3, max_length=50)
    project_ids: list[UUID] | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=6, max_length=128)


class PasswordResetResponse(BaseModel):
    detail: str
