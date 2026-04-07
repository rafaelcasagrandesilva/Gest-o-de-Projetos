from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin_role
from app.models.user import User
from app.services.audit_export_service import stream_audit_export_txt


router = APIRouter()


@router.get("/audit/export", summary="Exportar logs de auditoria em .txt (streaming)")
async def export_audit_logs(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin_role),
    date_start: datetime | None = Query(default=None, description="Início (created_at >=), UTC"),
    date_end: datetime | None = Query(default=None, description="Fim (created_at <=), UTC"),
    user_id: UUID | None = Query(default=None, description="Filtrar por autor do evento"),
    entity: str | None = Query(default=None, description="Filtrar por entidade (ex.: employee, user)"),
) -> StreamingResponse:
    async def gen() -> bytes:
        async for chunk in stream_audit_export_txt(
            db,
            date_start=date_start,
            date_end=date_end,
            user_id=user_id,
            entity=entity,
        ):
            yield chunk.encode("utf-8")

    fname = datetime.now(timezone.utc).strftime("audit-export-%Y%m%d-%H%M%S.txt")
    return StreamingResponse(
        gen(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "Cache-Control": "no-store",
        },
    )
