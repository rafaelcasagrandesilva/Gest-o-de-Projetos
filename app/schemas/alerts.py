from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampRead


class AlertRead(UUIDTimestampRead):
    project_id: UUID | None = None
    competencia: date | None = None
    alert_type: str
    severity: str
    message: str
    is_resolved: bool


class AlertResolveRequest(BaseModel):
    is_resolved: bool = Field(default=True)

