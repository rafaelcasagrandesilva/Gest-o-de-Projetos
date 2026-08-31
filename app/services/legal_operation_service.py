"""Jurídico — serviços da operação: timeline, agenda e Central de Trabalho.

Três serviços com responsabilidades separadas:

* `LegalTimelineService` — **a porta única de escrita da timeline** (M3). Nenhum outro código
  insere fato: se cada serviço escrever direto, em seis meses metade dos fatos não estará lá.
* `LegalEventService` — compromissos da agenda. Concluir um evento REGISTRA o fato
  correspondente (M4); adiar preserva o histórico apontando o novo (O7).
* `LegalWorkService` — a Central de Trabalho. Ela responde "o que preciso resolver hoje?" e por
  isso é uma FILA (O2): só quatro famílias de item podem ser críticas.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.legal import LegalCase, LegalCaseStatus
from app.models.legal_operation import (
    LegalAssignmentRole,
    LegalCaseAssignment,
    LegalEvent,
    LegalEventStatus,
    LegalEventType,
    LegalFactSource,
    LegalTimelineEntry,
    LegalTimelineEntryType,
)

# Estados de processo que consideramos ATIVOS para efeito de operação.
_ACTIVE_CASE_STATUSES = (
    LegalCaseStatus.EM_ANDAMENTO,
    LegalCaseStatus.COM_DECISAO,
    LegalCaseStatus.ACORDO,
    LegalCaseStatus.SUSPENSO,
)

# Dias sem qualquer fato registrado a partir dos quais o processo entra em "precisa de dono".
# Parâmetro do módulo: vira regra configurável quando o motor de regras existir (E6).
STALE_DAYS = 60


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    """Início e fim do dia em UTC — a comparação de agenda é sempre por dia inteiro."""
    return (
        datetime.combine(day, time.min, tzinfo=timezone.utc),
        datetime.combine(day, time.max, tzinfo=timezone.utc),
    )


class LegalTimelineService:
    """Porta ÚNICA de escrita da timeline (M3, O6). Fato registrado não se edita."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def record(
        self,
        *,
        case_id: UUID,
        entry_type: LegalTimelineEntryType,
        title: str,
        occurred_at: datetime | None = None,
        description: str | None = None,
        ref_type: str | None = None,
        ref_id: UUID | None = None,
        source: LegalFactSource = LegalFactSource.MANUAL,
        is_milestone: bool = False,
        created_by_id: UUID | None = None,
    ) -> LegalTimelineEntry:
        entry = LegalTimelineEntry(
            id=uuid4(),
            case_id=case_id,
            occurred_at=occurred_at or datetime.now(timezone.utc),
            entry_type=entry_type.value,
            title=title[:255],
            description=description,
            ref_type=ref_type,
            ref_id=ref_id,
            source=source.value,
            is_milestone=is_milestone,
            created_by_id=created_by_id,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def list_for_case(self, case_id: UUID, *, limit: int = 200) -> list[LegalTimelineEntry]:
        rows = await self.session.execute(
            select(LegalTimelineEntry)
            .where(LegalTimelineEntry.case_id == case_id)
            .order_by(LegalTimelineEntry.occurred_at.desc())
            .limit(limit)
        )
        return list(rows.scalars().all())

    async def last_fact_at(self, case_ids: list[UUID]) -> dict[UUID, datetime]:
        """Data do último fato por processo — base do sinal "sem movimentação" (O10)."""
        if not case_ids:
            return {}
        rows = await self.session.execute(
            select(LegalTimelineEntry.case_id, func.max(LegalTimelineEntry.occurred_at))
            .where(LegalTimelineEntry.case_id.in_(case_ids))
            .group_by(LegalTimelineEntry.case_id)
        )
        return {cid: dt for cid, dt in rows.all()}


class LegalEventService:
    """Compromissos da agenda (M4). Concluir vira fato; adiar preserva o histórico (O7)."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.timeline = LegalTimelineService(session)

    async def create(self, data: dict, *, actor_id: UUID | None = None) -> LegalEvent:
        event = LegalEvent(
            id=uuid4(),
            case_id=data.get("case_id"),
            event_type=str(data.get("event_type") or LegalEventType.OUTRO.value),
            title=str(data["title"]).strip()[:255],
            scheduled_for=data.get("scheduled_for"),
            due_at=data.get("due_at"),
            status=LegalEventStatus.AGENDADO.value,
            location=(data.get("location") or None),
            modality=(data.get("modality") or None),
            responsible_user_id=data.get("responsible_user_id") or actor_id,
            notes=(data.get("notes") or None),
            source=LegalFactSource.MANUAL.value,
            created_by_id=actor_id,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def get(self, event_id: UUID) -> LegalEvent | None:
        return (
            await self.session.execute(select(LegalEvent).where(LegalEvent.id == event_id))
        ).scalar_one_or_none()

    async def conclude(
        self, event_id: UUID, *, outcome: str | None, actor_id: UUID | None = None
    ) -> LegalEvent | None:
        """Evento concluído VIRA fato na timeline — é a passagem de compromisso para história."""
        event = await self.get(event_id)
        if event is None:
            return None
        event.status = LegalEventStatus.REALIZADO.value
        event.outcome = outcome
        if event.case_id:
            await self.timeline.record(
                case_id=event.case_id,
                entry_type=LegalTimelineEntryType.EVENTO_REALIZADO,
                title=event.title,
                description=outcome,
                occurred_at=event.scheduled_for or datetime.now(timezone.utc),
                ref_type="EVENT",
                ref_id=event.id,
                source=LegalFactSource.MANUAL,
                is_milestone=event.event_type == LegalEventType.AUDIENCIA.value,
                created_by_id=actor_id,
            )
        await self.session.flush()
        return event

    async def reschedule(
        self, event_id: UUID, *, new_datetime: datetime, reason: str | None, actor_id: UUID | None = None
    ) -> LegalEvent | None:
        """O7 — o evento adiado NÃO some: fica ADIADO e aponta o novo."""
        old = await self.get(event_id)
        if old is None:
            return None
        new = LegalEvent(
            id=uuid4(),
            case_id=old.case_id,
            event_type=old.event_type,
            title=old.title,
            scheduled_for=new_datetime,
            due_at=old.due_at,
            status=LegalEventStatus.AGENDADO.value,
            location=old.location,
            modality=old.modality,
            responsible_user_id=old.responsible_user_id,
            notes=old.notes,
            source=LegalFactSource.MANUAL.value,
            created_by_id=actor_id,
        )
        self.session.add(new)
        await self.session.flush()
        old.status = LegalEventStatus.ADIADO.value
        old.outcome = reason
        old.rescheduled_to_id = new.id
        if old.case_id:
            await self.timeline.record(
                case_id=old.case_id,
                entry_type=LegalTimelineEntryType.EVENTO_REALIZADO,
                title=f"{old.title} — adiado",
                description=reason,
                ref_type="EVENT",
                ref_id=old.id,
                created_by_id=actor_id,
            )
        await self.session.flush()
        return new

    async def list_between(
        self, *, start: datetime, end: datetime, only_open: bool = False
    ) -> list[LegalEvent]:
        stmt = select(LegalEvent).where(
            LegalEvent.scheduled_for.is_not(None),
            LegalEvent.scheduled_for >= start,
            LegalEvent.scheduled_for <= end,
        )
        if only_open:
            stmt = stmt.where(LegalEvent.status == LegalEventStatus.AGENDADO.value)
        rows = await self.session.execute(stmt.order_by(LegalEvent.scheduled_for.asc()))
        return list(rows.scalars().all())

    async def upcoming(self, *, limit: int = 8) -> list[LegalEvent]:
        now = datetime.now(timezone.utc)
        rows = await self.session.execute(
            select(LegalEvent)
            .where(
                LegalEvent.status == LegalEventStatus.AGENDADO.value,
                LegalEvent.scheduled_for.is_not(None),
                LegalEvent.scheduled_for >= now,
            )
            .order_by(LegalEvent.scheduled_for.asc())
            .limit(limit)
        )
        return list(rows.scalars().all())


class LegalWorkService:
    """Central de Trabalho — fila executável, não relatório (O2).

    Três blocos com horizontes distintos: o que quebra hoje, o que vem até o fim da semana e o
    que não tem dono. Regras de horizonte semanal (sem movimentação) ficam no terceiro bloco,
    nunca no primeiro — misturar horizontes é o que incha o painel.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.events = LegalEventService(session)
        self.timeline = LegalTimelineService(session)

    async def _case_titles(self, case_ids: set[UUID]) -> dict[UUID, tuple[str, str]]:
        ids = {c for c in case_ids if c}
        if not ids:
            return {}
        rows = await self.session.execute(
            select(LegalCase.id, LegalCase.case_number, LegalCase.claimant_name).where(LegalCase.id.in_(ids))
        )
        return {cid: (number or "—", claimant or "—") for cid, number, claimant in rows.all()}

    async def work_center(self, *, today: date | None = None) -> dict:
        today = today or datetime.now(timezone.utc).date()
        start_today, end_today = _day_bounds(today)
        _, end_week = _day_bounds(today + timedelta(days=7))

        # --- AGORA: vence hoje ou já venceu -------------------------------------------------
        agora_rows = (
            await self.session.execute(
                select(LegalEvent).where(
                    LegalEvent.status == LegalEventStatus.AGENDADO.value,
                    or_(
                        and_(LegalEvent.scheduled_for.is_not(None), LegalEvent.scheduled_for <= end_today),
                        and_(LegalEvent.due_at.is_not(None), LegalEvent.due_at <= end_today),
                    ),
                ).order_by(LegalEvent.scheduled_for.asc().nullsfirst())
            )
        ).scalars().all()

        # --- ESTA SEMANA: próximos sete dias -------------------------------------------------
        semana_rows = (
            await self.session.execute(
                select(LegalEvent).where(
                    LegalEvent.status == LegalEventStatus.AGENDADO.value,
                    LegalEvent.scheduled_for.is_not(None),
                    LegalEvent.scheduled_for > end_today,
                    LegalEvent.scheduled_for <= end_week,
                ).order_by(LegalEvent.scheduled_for.asc())
            )
        ).scalars().all()

        # --- PRECISA DE DONO: sem responsável ou sem fato há muito tempo ---------------------
        ativos = (
            await self.session.execute(
                select(LegalCase.id, LegalCase.case_number, LegalCase.claimant_name, LegalCase.status).where(
                    LegalCase.is_active.is_(True),
                    LegalCase.status.in_(_ACTIVE_CASE_STATUSES),
                )
            )
        ).all()
        ativos_ids = [row[0] for row in ativos]

        com_responsavel = set(
            (
                await self.session.execute(
                    select(LegalCaseAssignment.case_id).where(
                        LegalCaseAssignment.case_id.in_(ativos_ids or [uuid4()]),
                        LegalCaseAssignment.role == LegalAssignmentRole.RESPONSAVEL_JURIDICO.value,
                        LegalCaseAssignment.ended_at.is_(None),
                    )
                )
            ).scalars().all()
        )
        ultimo_fato = await self.timeline.last_fact_at(ativos_ids)
        limite = datetime.now(timezone.utc) - timedelta(days=STALE_DAYS)

        sem_dono, parados = [], []
        for cid, numero, reclamante, _status in ativos:
            if cid not in com_responsavel:
                sem_dono.append({"case_id": str(cid), "case_number": numero, "claimant": reclamante})
            last = ultimo_fato.get(cid)
            if last is not None and last < limite:
                parados.append(
                    {
                        "case_id": str(cid),
                        "case_number": numero,
                        "claimant": reclamante,
                        "days": (datetime.now(timezone.utc) - last).days,
                    }
                )
        parados.sort(key=lambda x: x["days"], reverse=True)

        titles = await self._case_titles({e.case_id for e in [*agora_rows, *semana_rows] if e.case_id})

        def as_item(event: LegalEvent) -> dict:
            numero, reclamante = titles.get(event.case_id, ("—", "—")) if event.case_id else (None, None)
            return {
                "id": str(event.id),
                "title": event.title,
                "event_type": event.event_type,
                "scheduled_for": event.scheduled_for,
                "due_at": event.due_at,
                "location": event.location,
                "modality": event.modality,
                "case_id": str(event.case_id) if event.case_id else None,
                "case_number": numero,
                "claimant": reclamante,
                "overdue": bool(
                    event.scheduled_for and event.scheduled_for < start_today
                ),
            }

        return {
            "today": today,
            "agora": [as_item(e) for e in agora_rows],
            "semana": [as_item(e) for e in semana_rows],
            "sem_dono": sem_dono,
            "parados": parados[:20],
            "stale_days": STALE_DAYS,
            "proximas_audiencias": [
                as_item(e)
                for e in await self.events.upcoming(limit=6)
                if e.event_type == LegalEventType.AUDIENCIA.value
            ],
        }

    async def executive_summary(self) -> dict:
        """Card executivo: cinco números, nada além (U1, U7)."""
        rows = (
            await self.session.execute(
                select(LegalCase.status, func.count(), func.sum(func.coalesce(LegalCase.amount_agreed, 0)))
                .where(LegalCase.is_active.is_(True))
                .group_by(LegalCase.status)
            )
        ).all()

        em_andamento = acordos = encerrados = 0
        valor_acordos = 0.0
        for status, quantidade, agreed in rows:
            valor = float(agreed or 0)
            if status in (LegalCaseStatus.EM_ANDAMENTO, LegalCaseStatus.COM_DECISAO, LegalCaseStatus.SUSPENSO):
                em_andamento += quantidade
            elif status in (LegalCaseStatus.ACORDO, LegalCaseStatus.ACORDO_FINALIZADO):
                acordos += quantidade
                valor_acordos += valor
            elif status is LegalCaseStatus.ENCERRADO:
                encerrados += quantidade

        # "Parcelas em aberto" ainda não têm entidade própria (Fase 2). Enquanto isso, o número
        # honesto é o saldo pendente registrado nos processos — e a tela diz de onde ele vem.
        pendente = (
            await self.session.execute(
                select(func.coalesce(func.sum(LegalCase.amount_pending), 0)).where(LegalCase.is_active.is_(True))
            )
        ).scalar_one()

        return {
            "em_andamento": em_andamento,
            "acordos": acordos,
            "valor_acordos": float(valor_acordos),
            "pendente": float(pendente or 0),
            "encerrados": encerrados,
        }
