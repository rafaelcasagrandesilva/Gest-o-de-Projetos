from __future__ import annotations

import logging
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.user import User
from app.utils.audit_diff import generate_diff
from app.utils.json_utils import make_json_serializable

logger = logging.getLogger(__name__)


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64] or None
    if request.client:
        return (request.client.host or "")[:64] or None
    return None


def _user_agent(request: Request | None) -> str | None:
    if request is None:
        return None
    ua = request.headers.get("user-agent")
    return (ua or "")[:512] or None


class AuditService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log_action(
        self,
        *,
        user: User | None,
        action: str,
        entity: str,
        entity_id: UUID,
        before: dict | None,
        after: dict | None,
        context: dict | None = None,
        request: Request | None = None,
        force_log: bool = False,
    ) -> AuditLog | None:
        """
        Persiste auditoria com field_changes (diff) e context legível.
        Falhas são engolidas (não quebram a transação principal) — log de erro apenas.

        force_log: True para eventos sem diff (ex.: login) que devem registrar sempre.
        """
        try:
            act = (action or "").strip().lower()
            ent = (entity or "").strip().lower()
            if not act or not ent:
                return None

            field_changes = generate_diff(before, after)
            if act == "update" and not field_changes and not force_log:
                return None

            fc = make_json_serializable(field_changes) if field_changes else None
            ctx = make_json_serializable(context) if context else None

            row = AuditLog(
                user_id=user.id if user else None,
                user_email=(user.email if user else None),
                action=act,
                entity=ent,
                entity_id=entity_id,
                field_changes=fc if fc else None,
                context=ctx,
                ip_address=_client_ip(request),
                user_agent=_user_agent(request),
            )
            self.session.add(row)
            await self.session.flush()
            return row
        except Exception:
            logger.exception(
                "audit.log_action falhou (ação não interrompida): entity=%s action=%s entity_id=%s",
                entity,
                action,
                entity_id,
            )
            return None
