from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CostCenterAliasCreate(BaseModel):
    alias_name: str = Field(..., min_length=1, max_length=255)
    target_cost_center: str = Field(..., min_length=1, max_length=255)


class CostCenterAliasRead(BaseModel):
    id: UUID
    alias_name: str
    target_cost_center: str
    created_by_user_id: UUID | None
    created_at: datetime
