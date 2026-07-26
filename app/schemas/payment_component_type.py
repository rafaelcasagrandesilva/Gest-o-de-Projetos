from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import UUIDTimestampRead

_CODE_RE = re.compile(r"^[a-z0-9_]+$")


class PaymentComponentTypeRead(UUIDTimestampRead):
    name: str
    code: str
    description: str | None
    is_active: bool
    display_order: int
    # Quantidade de utilizações (lançamentos que usam este tipo) — preenchida na listagem.
    usage_count: int = 0


class PaymentComponentTypeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    code: str = Field(..., min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool = True
    display_order: int = Field(default=0, ge=0)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("code")
    @classmethod
    def _norm_code(cls, v: str) -> str:
        s = v.strip().lower()
        if not _CODE_RE.match(s):
            raise ValueError("Código interno deve conter apenas letras minúsculas, números e underscore.")
        return s

    @field_validator("description")
    @classmethod
    def _strip_desc(cls, v: str | None) -> str | None:
        s = (v or "").strip()
        return s or None


class PaymentComponentTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None
    display_order: int | None = Field(default=None, ge=0)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else None

    @field_validator("code")
    @classmethod
    def _norm_code(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip().lower()
        if not _CODE_RE.match(s):
            raise ValueError("Código interno deve conter apenas letras minúsculas, números e underscore.")
        return s

    @field_validator("description")
    @classmethod
    def _strip_desc(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None
