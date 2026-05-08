from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampRead


class ProjectRead(UUIDTimestampRead):
    name: str
    code: str | None = None
    description: str | None = None
    cost_center: str | None = None
    is_active: bool = True
    closed_at: datetime | None = None
    deleted_at: datetime | None = None


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    code: str | None = Field(default=None, max_length=50)
    description: str | None = None
    cost_center: str | None = Field(default=None, max_length=255)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    code: str | None = Field(default=None, max_length=50)
    description: str | None = None
    cost_center: str | None = Field(default=None, max_length=255)

