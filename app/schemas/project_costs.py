from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampRead


class ProjectCostRead(UUIDTimestampRead):
    project_id: UUID
    name: str
    cost_type: str
    value: float
    cost_date: date
    category: str


class ProjectCostCreate(BaseModel):
    project_id: UUID
    name: str = Field(min_length=1, max_length=255)
    cost_type: Literal["fixo", "variavel"]
    value: float = Field(ge=0)
    cost_date: date
    category: str = Field(min_length=1, max_length=100)


class ProjectCostUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    cost_type: Literal["fixo", "variavel"] | None = None
    value: float | None = Field(default=None, ge=0)
    cost_date: date | None = None
    category: str | None = Field(default=None, min_length=1, max_length=100)
