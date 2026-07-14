from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import UUIDTimestampRead


class RoleRead(UUIDTimestampRead):
    name: str
    description: str | None = None
    is_system: bool = False
    is_active: bool = True
    user_count: int = 0
    permission_names: list[str] = []


class UserRead(UUIDTimestampRead):
    email: EmailStr
    full_name: str
    is_active: bool
    deleted_at: datetime | None = None
    role_names: list[str] = []
    project_ids: list[UUID] = []
    linked_projects: list[UUID] = Field(
        default_factory=list,
        description="Alias explícito dos projetos vinculados usado pelo contexto de sessão.",
    )
    permission_names: list[str] = []
    current_workspace: str = Field(default="projects", description="Workspace ativo saneado pelo backend.")
    default_workspace: str = Field(default="projects", description="Workspace padrão permitido para o usuário.")
    session_version: int = Field(default=2, description="Versão do contrato de sessão/token aceito pelo backend.")
    has_all_projects_linked: bool = Field(
        default=False,
        description="Vínculo cobre todos os projetos do sistema (visão consolidada no dashboard).",
    )
    is_superuser: bool = Field(
        default=False,
        description="Conta na lista operacional de super usuários (ações críticas; não é o mesmo que role ADMIN).",
    )


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
    is_active: bool = True
    # Lista completa das permissões do perfil. Se `base_role_id` for informado e permission_names for
    # None, as permissões são copiadas do perfil base (duplicação).
    permission_names: list[str] | None = None
    base_role_id: UUID | None = None


class RoleUpdate(BaseModel):
    # `name` só é aceito para perfis não-sistema (renome bloqueado nos de sistema).
    name: str | None = Field(default=None, min_length=2, max_length=50)
    description: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    permission_names: list[str] | None = None


class AssignRoleRequest(BaseModel):
    role_name: str = Field(min_length=3, max_length=50)
    project_ids: list[UUID] | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=6, max_length=128)


class PasswordResetResponse(BaseModel):
    detail: str
