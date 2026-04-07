"""Exportação de audit_logs em texto legível com streaming (paginação interna)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import Select, and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog

logger = logging.getLogger(__name__)

PAGE_SIZE = 500


def _fmt(v: object) -> str:
    if v is None:
        return "—"
    return str(v)


def _format_context_block(ctx: dict | None) -> str:
    if not ctx:
        return ""
    lines: list[str] = []
    label_map = {
        "project_name": "Projeto",
        "employee_name": "Colaborador",
        "empregado": "Colaborador",
        "competencia": "Competência",
        "tipo": "Tipo",
        "descricao": "Descrição",
        "scenario": "Cenário",
        "role_name": "Perfil",
        "permission_names": "Permissões",
        "project_ids": "Projetos (IDs)",
    }
    for k, v in sorted(ctx.items()):
        if k == "legacy":
            continue
        label = label_map.get(k, k.replace("_", " ").title())
        if isinstance(v, (list, dict)):
            lines.append(f"- {label}: {_fmt(v)}")
        else:
            lines.append(f"- {label}: {_fmt(v)}")
    if not lines:
        return ""
    return "Contexto:\n" + "\n".join(lines) + "\n"


def _format_field_changes_block(fc: dict | None) -> str:
    if not fc:
        return "Alterações:\n(nenhuma alteração de campo rastreada)\n"
    lines: list[str] = []
    for field in sorted(fc.keys()):
        ch = fc[field]
        if isinstance(ch, dict) and "before" in ch and "after" in ch:
            lines.append(f"- {field}: {_fmt(ch['before'])} → {_fmt(ch['after'])}")
        else:
            lines.append(f"- {field}: {_fmt(ch)}")
    return "Alterações:\n" + ("\n".join(lines) if lines else "(nenhuma)") + "\n"


def _format_record(row: AuditLog) -> str:
    ts = row.created_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts_local = ts.strftime("%Y-%m-%d %H:%M")
    who = row.user_email or "—"
    name_part = ""
    if row.user and getattr(row.user, "full_name", None):
        name_part = f"{row.user.full_name} "
    header = f"[{ts_local}]\nUsuário: {name_part}({who})\n"
    header += f"Ação: {row.action.upper()}\nEntidade: {row.entity}\nRegistro: {row.entity_id}\n\n"
    body = _format_field_changes_block(row.field_changes)
    ctx = _format_context_block(row.context)
    if ctx:
        body += "\n" + ctx
    ip = row.ip_address or "—"
    ua = row.user_agent or "—"
    body += f"\nIP: {ip}\nUser-Agent: {ua}\n"
    body += "\n" + "-" * 40 + "\n\n"
    return header + body


def _build_select(
    *,
    date_start: datetime | None,
    date_end: datetime | None,
    user_id: UUID | None,
    entity: str | None,
) -> Select[tuple[AuditLog]]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.asc())
    cond = []
    if date_start is not None:
        cond.append(AuditLog.created_at >= date_start)
    if date_end is not None:
        cond.append(AuditLog.created_at <= date_end)
    if user_id is not None:
        cond.append(AuditLog.user_id == user_id)
    if entity:
        cond.append(AuditLog.entity == entity.strip().lower())
    if cond:
        stmt = stmt.where(and_(*cond))
    return stmt


async def stream_audit_export_txt(
    session: AsyncSession,
    *,
    date_start: datetime | None = None,
    date_end: datetime | None = None,
    user_id: UUID | None = None,
    entity: str | None = None,
) -> AsyncIterator[str]:
    """Yields chunks de texto para StreamingResponse (sem carregar tudo em memória)."""

    offset = 0
    header = "=== RELATÓRIO DE AUDITORIA ===\n"
    header += f"Gerado em: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
    if date_start:
        header += f"Filtro início: {date_start.isoformat()}\n"
    if date_end:
        header += f"Filtro fim: {date_end.isoformat()}\n"
    if user_id:
        header += f"Filtro usuário: {user_id}\n"
    if entity:
        header += f"Filtro entidade: {entity}\n"
    header += "\n" + "=" * 40 + "\n\n"
    yield header

    while True:
        stmt = (
            _build_select(
                date_start=date_start, date_end=date_end, user_id=user_id, entity=entity
            )
            .offset(offset)
            .limit(PAGE_SIZE)
            .options(selectinload(AuditLog.user))
        )
        try:
            res = await session.execute(stmt)
            rows = list(res.scalars().all())
        except Exception:
            logger.exception("audit export: falha na página offset=%s", offset)
            yield "\n[Erro ao ler página de auditoria. Consulte os logs do servidor.]\n"
            break
        if not rows:
            break
        for row in rows:
            yield _format_record(row)
        offset += PAGE_SIZE
        if len(rows) < PAGE_SIZE:
            break
