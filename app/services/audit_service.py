from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.utils.json_utils import make_json_serializable


class AuditService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(
        self,
        *,
        actor_user_id: UUID | None,
        action: str,
        entity: str,
        entity_id: UUID,
        before: dict | None,
        after: dict | None,
    ) -> AuditLog:
        if before is not None:
            before = make_json_serializable(before)
        if after is not None:
            after = make_json_serializable(after)
        row = AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            before=before,
            after=after,
        )
        self.session.add(row)
        await self.session.flush()
        return row

