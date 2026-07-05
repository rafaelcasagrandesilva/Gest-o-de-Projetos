from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import UUIDTimestampRead

# Perfis de operação suportados (cada um possui um Operation Handler).
# Adicionar um novo perfil = cadastrar instituição + implementar o handler.
KNOWN_OPERATION_PROFILES = ("LEPTA", "DAYCOVAL")


class AdvanceInstitutionRead(UUIDTimestampRead):
    name: str
    institution_type: str
    operation_profile: str
    is_active: bool


class AdvanceInstitutionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    institution_type: str = Field(default="OUTROS", max_length=64)
    operation_profile: str = Field(..., max_length=64)
    is_active: bool = True

    @field_validator("name", "institution_type")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("operation_profile")
    @classmethod
    def _profile_ok(cls, v: str) -> str:
        s = v.strip().upper()
        if s not in KNOWN_OPERATION_PROFILES:
            raise ValueError(f"operation_profile inválido. Use um de: {', '.join(KNOWN_OPERATION_PROFILES)}.")
        return s


class AdvanceInstitutionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    institution_type: str | None = Field(default=None, max_length=64)
    operation_profile: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None

    @field_validator("name", "institution_type")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else None

    @field_validator("operation_profile")
    @classmethod
    def _profile_ok(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip().upper()
        if s not in KNOWN_OPERATION_PROFILES:
            raise ValueError(f"operation_profile inválido. Use um de: {', '.join(KNOWN_OPERATION_PROFILES)}.")
        return s
