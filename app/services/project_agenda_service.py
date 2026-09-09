"""Agenda do workspace Projetos — compromissos, participantes e anexos.

Módulo DELIBERADAMENTE isolado da agenda do Jurídico: tabelas, vocabulário e permissões
próprios, e nenhum registro de uma agenda aparece na outra (ver docs/ETAPA0_AGENDA_PROJETOS.md).
A semelhança entre as duas telas é visual, não de código nem de dado.

Um mesmo registro atende os dois usos que motivaram o módulo, porque o que os une é **data,
gente e cobrança**: a reunião (`starts_at` + participantes + a ata depois) e a obrigação
atribuída (`owner_user_id` + `due_at` + `description`).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.project import Project
from app.models.project_agenda import (
    CommitmentKind,
    CommitmentOutcome,
    CommitmentModality,
    CommitmentStatus,
    ProjectCommitment,
    ProjectCommitmentAttachment,
    ProjectCommitmentOccurrence,
    ProjectCommitmentParticipant,
)
from app.models.user import User

ALLOWED_SUFFIXES = {".pdf", ".doc", ".docx", ".odt", ".txt", ".jpg", ".jpeg", ".png", ".webp", ".heic"}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9À-ÿ ._-]")

#: Status que ainda cobram alguém. CANCELADO e CONCLUIDO saem das pendências.
OPEN_STATUSES = (CommitmentStatus.AGENDADO.value, CommitmentStatus.ADIADO.value)


def _clean_file_name(raw: str) -> str:
    name = Path(raw or "").name.strip() or "anexo"
    return _SAFE_NAME.sub("_", name)[:255]


def _as_utc(value: datetime | None) -> datetime | None:
    """Datas comparáveis: o banco guarda com fuso, e entrada sem fuso é tratada como UTC."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class ProjectAgendaService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------ leitura

    async def _load(self, commitment_id: UUID) -> ProjectCommitment | None:
        return (
            await self.db.execute(
                select(ProjectCommitment)
                .where(ProjectCommitment.id == commitment_id)
                .options(
                    selectinload(ProjectCommitment.participants),
                    selectinload(ProjectCommitment.attachments),
                )
            )
        ).scalars().first()

    async def _names(self, ids: set[UUID]) -> dict[UUID, str]:
        """Nome dos usuários citados, numa consulta só (a lista tem N compromissos)."""
        if not ids:
            return {}
        rows = (
            await self.db.execute(select(User.id, User.full_name).where(User.id.in_(ids)))
        ).all()
        return {uid: nome for uid, nome in rows}

    async def _projects(self, ids: set[UUID]) -> dict[UUID, str]:
        if not ids:
            return {}
        rows = (await self.db.execute(select(Project.id, Project.name).where(Project.id.in_(ids)))).all()
        return {pid: nome for pid, nome in rows}

    async def to_read(self, rows: list[ProjectCommitment], *, hoje: datetime | None = None) -> list[dict]:
        agora = hoje or datetime.now(timezone.utc)
        user_ids: set[UUID] = set()
        project_ids: set[UUID] = set()
        for r in rows:
            if r.owner_user_id:
                user_ids.add(r.owner_user_id)
            if r.project_id:
                project_ids.add(r.project_id)
            user_ids.update(p.user_id for p in (r.participants or []))
        nomes = await self._names(user_ids)
        projetos = await self._projects(project_ids)

        out: list[dict] = []
        for r in rows:
            prazo = _as_utc(r.due_at) or _as_utc(r.starts_at)
            # Atrasado é o que TEM prazo, já passou e ninguém fechou. Compromisso sem data
            # nenhuma (backlog) nunca atrasa — só espera.
            atrasado = bool(prazo and prazo < agora and r.status in OPEN_STATUSES)
            out.append(
                {
                    "id": r.id,
                    "kind": r.kind,
                    "title": r.title,
                    "description": r.description,
                    "starts_at": r.starts_at,
                    "due_at": r.due_at,
                    "all_day": r.all_day,
                    "duration_minutes": r.duration_minutes,
                    "location": r.location,
                    "modality": r.modality,
                    "project_id": r.project_id,
                    "project_name": projetos.get(r.project_id) if r.project_id else None,
                    "owner_user_id": r.owner_user_id,
                    "owner_name": nomes.get(r.owner_user_id) if r.owner_user_id else None,
                    "external_participants": r.external_participants,
                    "status": r.status,
                    "completed_at": r.completed_at,
                    "completion_note": r.completion_note,
                    "is_overdue": atrasado,
                    "participants": [
                        {"user_id": p.user_id, "full_name": nomes.get(p.user_id, "—")}
                        for p in sorted(r.participants or [], key=lambda x: nomes.get(x.user_id, ""))
                    ],
                    "attachments": [
                        {
                            "id": a.id,
                            "file_name": a.file_name,
                            "mime_type": a.mime_type,
                            "size_bytes": a.size_bytes,
                            "is_minutes": a.is_minutes,
                            "created_at": a.created_at,
                        }
                        for a in sorted(r.attachments or [], key=lambda x: x.created_at)
                    ],
                    "series_id": r.series_id,
                    "created_by_id": r.created_by_id,
                }
            )
        return out

    async def list_between(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
        only_user_id: UUID | None = None,
        project_id: UUID | None = None,
        kind: str | None = None,
        status: str | None = None,
    ) -> list[ProjectCommitment]:
        """Compromissos da janela. `only_user_id` = "só os meus": responsável OU participante."""
        q = select(ProjectCommitment).options(
            selectinload(ProjectCommitment.participants),
            selectinload(ProjectCommitment.attachments),
        )
        if start is not None:
            ini = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
            # A data que posiciona o compromisso no calendário é `starts_at` ou, na falta,
            # `due_at` — por isso a janela olha as duas.
            q = q.where(
                or_(ProjectCommitment.starts_at >= ini, ProjectCommitment.due_at >= ini)
            )
        if end is not None:
            fim = datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc)
            q = q.where(
                or_(ProjectCommitment.starts_at <= fim, ProjectCommitment.due_at <= fim)
            )
        if project_id is not None:
            q = q.where(ProjectCommitment.project_id == project_id)
        if kind:
            q = q.where(ProjectCommitment.kind == kind)
        if status:
            q = q.where(ProjectCommitment.status == status)
        if only_user_id is not None:
            envolvido = select(ProjectCommitmentParticipant.commitment_id).where(
                ProjectCommitmentParticipant.user_id == only_user_id
            )
            q = q.where(
                or_(
                    ProjectCommitment.owner_user_id == only_user_id,
                    ProjectCommitment.id.in_(envolvido),
                )
            )
        q = q.order_by(
            ProjectCommitment.starts_at.asc().nulls_last(), ProjectCommitment.due_at.asc().nulls_last()
        )
        return list((await self.db.execute(q)).scalars().unique().all())

    async def counters(self, *, user_id: UUID) -> dict:
        """Atrasados e desta semana — os meus e os de todos. É o que dá vida à atribuição."""
        agora = datetime.now(timezone.utc)
        fim_semana = agora + timedelta(days=7)
        todos = await self.list_between()
        meus = {c.id for c in await self.list_between(only_user_id=user_id)}

        def conta(pred) -> tuple[int, int]:
            t = [c for c in todos if pred(c)]
            return len(t), len([c for c in t if c.id in meus])

        def atrasado(c: ProjectCommitment) -> bool:
            prazo = _as_utc(c.due_at) or _as_utc(c.starts_at)
            return bool(prazo and prazo < agora and c.status in OPEN_STATUSES)

        def na_semana(c: ProjectCommitment) -> bool:
            prazo = _as_utc(c.due_at) or _as_utc(c.starts_at)
            return bool(prazo and agora <= prazo <= fim_semana and c.status in OPEN_STATUSES)

        atrasados, meus_atrasados = conta(atrasado)
        semana, minha_semana = conta(na_semana)
        return {
            "overdue": atrasados,
            "overdue_mine": meus_atrasados,
            "this_week": semana,
            "this_week_mine": minha_semana,
        }

    # ------------------------------------------------------------------ escrita

    @staticmethod
    def _validate(data: dict) -> None:
        if data.get("kind") not in {k.value for k in CommitmentKind}:
            raise HTTPException(status_code=400, detail="Tipo de compromisso inválido.")
        if not (data.get("title") or "").strip():
            raise HTTPException(status_code=400, detail="Informe o título do compromisso.")
        modality = data.get("modality")
        if modality and modality not in {m.value for m in CommitmentModality}:
            raise HTTPException(status_code=400, detail="Modalidade inválida.")
        # Um compromisso sem data nenhuma é backlog: aparece na lista, nunca no calendário —
        # e nunca atrasa. É permitido de propósito (ideia registrada antes de ter data).
        if data.get("starts_at") and data.get("due_at"):
            if _as_utc(data["due_at"]) < _as_utc(data["starts_at"]):
                raise HTTPException(status_code=400, detail="O prazo não pode ser anterior ao início.")

    async def _set_participants(self, commitment: ProjectCommitment, user_ids: list[UUID] | None) -> None:
        """Substitui a lista de participantes. O responsável entra sempre — ele participa do
        que responde, e sem isso não veria o item no filtro "só os meus"."""
        desejados = set(user_ids or [])
        if commitment.owner_user_id:
            desejados.add(commitment.owner_user_id)
        if desejados:
            existem = set(
                (await self.db.execute(select(User.id).where(User.id.in_(desejados)))).scalars().all()
            )
            invalidos = desejados - existem
            if invalidos:
                raise HTTPException(status_code=400, detail="Participante inexistente.")
        await self.db.execute(
            delete(ProjectCommitmentParticipant).where(
                ProjectCommitmentParticipant.commitment_id == commitment.id
            )
        )
        for uid in desejados:
            self.db.add(ProjectCommitmentParticipant(commitment_id=commitment.id, user_id=uid))
        await self.db.flush()

    async def create(self, *, data: dict, actor_id: UUID | None) -> ProjectCommitment:
        self._validate(data)
        row = ProjectCommitment(
            kind=data["kind"],
            title=data["title"].strip(),
            description=(data.get("description") or None),
            starts_at=data.get("starts_at"),
            due_at=data.get("due_at"),
            all_day=bool(data.get("all_day", False)),
            duration_minutes=data.get("duration_minutes"),
            location=(data.get("location") or None),
            modality=(data.get("modality") or None),
            project_id=data.get("project_id"),
            owner_user_id=data.get("owner_user_id"),
            external_participants=(data.get("external_participants") or None),
            series_id=data.get("series_id"),
            status=CommitmentStatus.AGENDADO.value,
            created_by_id=actor_id,
        )
        self.db.add(row)
        await self.db.flush()
        await self._set_participants(row, data.get("participant_ids"))
        return row

    async def update(self, *, commitment_id: UUID, data: dict) -> ProjectCommitment | None:
        row = await self._load(commitment_id)
        if row is None:
            return None
        merged = {
            "kind": data.get("kind", row.kind),
            "title": data.get("title", row.title),
            "modality": data.get("modality", row.modality),
            "starts_at": data.get("starts_at", row.starts_at),
            "due_at": data.get("due_at", row.due_at),
        }
        self._validate(merged)
        for campo in (
            "kind", "title", "description", "starts_at", "due_at", "all_day", "duration_minutes",
            "location", "modality", "project_id", "owner_user_id", "external_participants", "status",
        ):
            if campo in data:
                setattr(row, campo, data[campo])
        if "participant_ids" in data:
            await self._set_participants(row, data["participant_ids"])
        elif "owner_user_id" in data:
            # Trocou o responsável: ele precisa entrar como participante do que passou a responder.
            await self._set_participants(row, [p.user_id for p in (row.participants or [])])
        await self.db.flush()
        return row

    async def complete(self, *, commitment_id: UUID, note: str | None) -> ProjectCommitment | None:
        row = await self._load(commitment_id)
        if row is None:
            return None
        row.status = CommitmentStatus.CONCLUIDO.value
        row.completed_at = datetime.now(timezone.utc)
        row.completion_note = (note or None)
        await self.db.flush()
        return row

    async def reopen(self, *, commitment_id: UUID) -> ProjectCommitment | None:
        row = await self._load(commitment_id)
        if row is None:
            return None
        row.status = CommitmentStatus.AGENDADO.value
        row.completed_at = None
        row.completion_note = None
        await self.db.flush()
        return row

    async def delete(self, *, commitment_id: UUID) -> bool:
        row = await self._load(commitment_id)
        if row is None:
            return False
        # Anexos somem do disco ANTES do registro, senão ficam órfãos no volume.
        await self.purge_attachments(commitment_id)
        await self.db.delete(row)
        await self.db.flush()
        return True

    # ------------------------------------------------------------------ anexos

    def base_dir(self) -> Path:
        return Path(settings.project_agenda_attachment_dir)

    def disk_path(self, row: ProjectCommitmentAttachment) -> Path:
        return (self.base_dir() / row.stored_path).resolve()

    async def add_attachment(
        self,
        *,
        commitment_id: UUID,
        file_name: str,
        body: bytes,
        mime_type: str | None,
        is_minutes: bool,
        actor_id: UUID | None,
    ) -> ProjectCommitmentAttachment:
        clean = _clean_file_name(file_name)
        if Path(clean).suffix.lower() not in ALLOWED_SUFFIXES:
            raise HTTPException(
                status_code=400,
                detail=f"{clean}: formato não aceito. Envie PDF, documento de texto ou imagem.",
            )
        limite = settings.project_agenda_attachment_max_bytes
        if len(body) > limite:
            raise HTTPException(
                status_code=413, detail=f"{clean}: excede o limite de {limite // (1024 * 1024)} MB."
            )
        if not body:
            raise HTTPException(status_code=400, detail=f"{clean}: arquivo vazio.")

        # Subdiretório por compromisso, nome de arquivo sorteado: dois anexos com o mesmo nome
        # não se sobrescrevem, e o nome original fica só no banco (exibição).
        rel = Path(str(commitment_id)) / f"{uuid4().hex}{Path(clean).suffix.lower()}"
        destino = self.base_dir() / rel
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(body)

        row = ProjectCommitmentAttachment(
            commitment_id=commitment_id,
            file_name=clean,
            stored_path=str(rel),
            mime_type=mime_type,
            size_bytes=len(body),
            is_minutes=is_minutes,
            uploaded_by_id=actor_id,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def get_attachment(
        self, *, commitment_id: UUID, attachment_id: UUID
    ) -> ProjectCommitmentAttachment | None:
        return (
            await self.db.execute(
                select(ProjectCommitmentAttachment).where(
                    ProjectCommitmentAttachment.id == attachment_id,
                    ProjectCommitmentAttachment.commitment_id == commitment_id,
                )
            )
        ).scalars().first()

    async def delete_attachment(self, *, commitment_id: UUID, attachment_id: UUID) -> bool:
        row = await self.get_attachment(commitment_id=commitment_id, attachment_id=attachment_id)
        if row is None:
            return False
        caminho = self.disk_path(row)
        await self.db.delete(row)
        await self.db.flush()
        caminho.unlink(missing_ok=True)
        return True

    async def purge_attachments(self, commitment_id: UUID) -> None:
        rows = (
            await self.db.execute(
                select(ProjectCommitmentAttachment).where(
                    ProjectCommitmentAttachment.commitment_id == commitment_id
                )
            )
        ).scalars().all()
        for row in rows:
            self.disk_path(row).unlink(missing_ok=True)

    # ------------------------------------------------------------------ pauta da reunião

    async def agenda_items(self, meeting_id: UUID) -> list[dict]:
        """Itens em pauta nesta reunião, com o desfecho DELA e o histórico de quantas vezes rolou.

        Um item aparece aqui por ter uma OCORRÊNCIA nesta reunião — foi tratado nela, seja porque
        nasceu aqui ou porque veio estendido de uma anterior.
        """
        ocorrencias = (
            await self.db.execute(
                select(ProjectCommitmentOccurrence)
                .where(ProjectCommitmentOccurrence.meeting_id == meeting_id)
                .order_by(ProjectCommitmentOccurrence.created_at.asc())
            )
        ).scalars().all()
        if not ocorrencias:
            return []

        ids = [o.commitment_id for o in ocorrencias]
        itens = {
            c.id: c
            for c in (
                await self.db.execute(
                    select(ProjectCommitment)
                    .where(ProjectCommitment.id.in_(ids))
                    .options(
                        selectinload(ProjectCommitment.participants),
                        selectinload(ProjectCommitment.attachments),
                    )
                )
            ).scalars().unique().all()
        }
        # Todas as passagens desses itens, para dizer "2ª vez" e para onde foi estendido.
        todas = (
            await self.db.execute(
                select(ProjectCommitmentOccurrence)
                .where(ProjectCommitmentOccurrence.commitment_id.in_(ids))
                .order_by(ProjectCommitmentOccurrence.created_at.asc())
            )
        ).scalars().all()
        por_item: dict[UUID, list[ProjectCommitmentOccurrence]] = {}
        for o in todas:
            por_item.setdefault(o.commitment_id, []).append(o)

        reunioes = {
            m.id: m
            for m in (
                await self.db.execute(
                    select(ProjectCommitment).where(
                        ProjectCommitment.id.in_([o.meeting_id for o in todas])
                    )
                )
            ).scalars().all()
        }

        lidos = {d["id"]: d for d in await self.to_read([itens[i] for i in ids if i in itens])}
        saida: list[dict] = []
        for occ in ocorrencias:
            item = lidos.get(occ.commitment_id)
            if item is None:
                continue
            historico = por_item.get(occ.commitment_id, [])
            posicao = next((i for i, o in enumerate(historico) if o.id == occ.id), 0) + 1
            seguinte = historico[posicao] if posicao < len(historico) else None
            anterior = historico[posicao - 2] if posicao >= 2 else None
            saida.append(
                {
                    **item,
                    "occurrence_id": occ.id,
                    "outcome": occ.outcome,
                    #: 1 = nasceu aqui; 2+ = veio estendido.
                    "occurrence_number": posicao,
                    "total_occurrences": len(historico),
                    "extended_to_meeting_id": seguinte.meeting_id if seguinte else None,
                    "extended_to_date": (
                        _meeting_date(reunioes.get(seguinte.meeting_id)) if seguinte else None
                    ),
                    "came_from_date": (
                        _meeting_date(reunioes.get(anterior.meeting_id)) if anterior else None
                    ),
                }
            )
        return saida

    async def add_agenda_item(self, *, meeting_id: UUID, data: dict, actor_id: UUID | None):
        """Cria o item E a sua primeira passagem por esta reunião."""
        item = await self.create(data={**data, "kind": "OBRIGACAO"}, actor_id=actor_id)
        self.db.add(
            ProjectCommitmentOccurrence(
                commitment_id=item.id, meeting_id=meeting_id, outcome=CommitmentOutcome.OPEN.value
            )
        )
        await self.db.flush()
        return item

    async def set_outcome(
        self, *, occurrence_id: UUID, outcome: str, next_meeting_id: UUID | None = None
    ) -> dict:
        """Marca o desfecho do item NAQUELA reunião.

        `EXTENDED` exige a próxima reunião e cria a passagem seguinte — é o que faz a pauta da
        reunião que vem já nascer montada. `DONE` fecha o compromisso (sai dos contadores de
        atraso e do "só os meus"); `PARTIAL` mantém o item aberto, porque ainda há o que cobrar.
        """
        if outcome not in {o.value for o in CommitmentOutcome}:
            raise HTTPException(status_code=400, detail="Desfecho inválido.")
        occ = await self.db.get(ProjectCommitmentOccurrence, occurrence_id)
        if occ is None:
            raise HTTPException(status_code=404, detail="Item não encontrado nesta reunião.")

        occ.outcome = outcome
        item = await self._load(occ.commitment_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Item não encontrado.")

        if outcome == CommitmentOutcome.DONE.value:
            item.status = CommitmentStatus.CONCLUIDO.value
            item.completed_at = datetime.now(timezone.utc)
        else:
            item.status = CommitmentStatus.AGENDADO.value
            item.completed_at = None

        criada = False
        if outcome == CommitmentOutcome.EXTENDED.value:
            if next_meeting_id is None:
                raise HTTPException(
                    status_code=400, detail="Informe a reunião para a qual o item foi estendido."
                )
            proxima = await self.db.get(ProjectCommitment, next_meeting_id)
            if proxima is None or proxima.kind != CommitmentKind.REUNIAO.value:
                raise HTTPException(status_code=400, detail="Reunião de destino inválida.")
            ja_existe = (
                await self.db.execute(
                    select(ProjectCommitmentOccurrence).where(
                        ProjectCommitmentOccurrence.commitment_id == occ.commitment_id,
                        ProjectCommitmentOccurrence.meeting_id == next_meeting_id,
                    )
                )
            ).scalars().first()
            if ja_existe is None:
                self.db.add(
                    ProjectCommitmentOccurrence(
                        commitment_id=occ.commitment_id,
                        meeting_id=next_meeting_id,
                        outcome=CommitmentOutcome.OPEN.value,
                    )
                )
                criada = True
            # O prazo passa a ser a próxima reunião: é o que o time combina na prática
            # ("me traz até a reunião que vem"), e mantém o item cobrando na data certa.
            if proxima.starts_at:
                item.due_at = proxima.starts_at

        await self.db.flush()
        return {"outcome": outcome, "next_occurrence_created": criada}

    async def upcoming_meetings(self, *, after: datetime | None = None) -> list[ProjectCommitment]:
        """Reuniões futuras, para escolher o destino de um item estendido."""
        base = after or datetime.now(timezone.utc)
        return list(
            (
                await self.db.execute(
                    select(ProjectCommitment)
                    .where(
                        ProjectCommitment.kind == CommitmentKind.REUNIAO.value,
                        ProjectCommitment.starts_at > base,
                        ProjectCommitment.status != CommitmentStatus.CANCELADO.value,
                    )
                    .order_by(ProjectCommitment.starts_at.asc())
                    .limit(20)
                )
            ).scalars().all()
        )

    # ------------------------------------------------------------------ recorrência

    #: Teto de ocorrências criadas de uma vez — um ano de reunião semanal.
    MAX_OCCURRENCES = 52

    async def create_series(
        self, *, data: dict, every_weeks: int, count: int, actor_id: UUID | None
    ) -> list[ProjectCommitment]:
        """Cria N ocorrências da mesma repetição, todas com o mesmo `series_id`.

        As ocorrências são MATERIALIZADAS (uma linha por semana), e não calculadas na leitura:
        cada reunião precisa carregar a sua própria ata, os seus participantes e a sua pauta —
        coisas que uma data virtual não guardaria. O preço é que a série não é editável em bloco;
        o ganho é que remarcar uma quarta não toca nas outras, que é o que a gestão pediu.
        """
        if every_weeks < 1:
            raise HTTPException(status_code=400, detail="O intervalo deve ser de ao menos 1 semana.")
        if count < 1 or count > self.MAX_OCCURRENCES:
            raise HTTPException(
                status_code=400,
                detail=f"A repetição aceita de 1 a {self.MAX_OCCURRENCES} ocorrências.",
            )
        inicio = data.get("starts_at")
        if inicio is None:
            raise HTTPException(
                status_code=400, detail="Informe a data e a hora da primeira ocorrência."
            )

        serie = uuid4()
        criadas: list[ProjectCommitment] = []
        participantes = data.get("participant_ids")
        for i in range(count):
            deslocamento = timedelta(weeks=every_weeks * i)
            criadas.append(
                await self.create(
                    data={
                        **data,
                        "series_id": serie,
                        "starts_at": inicio + deslocamento,
                        # O prazo, quando existe, acompanha a ocorrência — senão todas herdariam
                        # a data-limite da primeira e nasceriam atrasadas.
                        "due_at": (data["due_at"] + deslocamento) if data.get("due_at") else None,
                        "participant_ids": participantes,
                    },
                    actor_id=actor_id,
                )
            )
        return criadas

    async def next_in_series(
        self, *, meeting_id: UUID
    ) -> ProjectCommitment | None:
        """Próxima ocorrência da MESMA série, para levar um item adiante em um clique."""
        atual = await self.db.get(ProjectCommitment, meeting_id)
        if atual is None or atual.series_id is None or atual.starts_at is None:
            return None
        return (
            await self.db.execute(
                select(ProjectCommitment)
                .where(
                    ProjectCommitment.series_id == atual.series_id,
                    ProjectCommitment.id != atual.id,
                    ProjectCommitment.starts_at > atual.starts_at,
                    ProjectCommitment.status != CommitmentStatus.CANCELADO.value,
                )
                .order_by(ProjectCommitment.starts_at.asc())
                .limit(1)
            )
        ).scalars().first()

    async def _series_rows(self, commitment_id: UUID) -> tuple[ProjectCommitment, list[ProjectCommitment]] | None:
        """A ocorrência pedida e TODAS as irmãs dela, em ordem de data."""
        atual = await self._load(commitment_id)
        if atual is None or atual.series_id is None:
            return None
        irmas = (
            await self.db.execute(
                select(ProjectCommitment)
                .options(selectinload(ProjectCommitment.participants))
                .where(ProjectCommitment.series_id == atual.series_id)
                .order_by(ProjectCommitment.starts_at.asc())
            )
        ).scalars().all()
        return atual, list(irmas)

    @staticmethod
    def _cadencia_semanas(ocorrencias: list[ProjectCommitment]) -> int:
        """Intervalo da série, em semanas, lido do intervalo mais comum entre as ocorrências.

        Não guardamos a regra de repetição: uma ocorrência remarcada à mão tornaria o registro
        mentiroso. O intervalo MAIS COMUM sobrevive a essas exceções — mover uma quarta para a
        quinta não faz a série virar quinzenal.
        """
        datas = sorted(o.starts_at for o in ocorrencias if o.starts_at)
        if len(datas) < 2:
            return 1
        vaos: dict[int, int] = {}
        for anterior, seguinte in zip(datas, datas[1:]):
            semanas = max(1, round((seguinte - anterior).days / 7))
            vaos[semanas] = vaos.get(semanas, 0) + 1
        return max(vaos.items(), key=lambda kv: (kv[1], -kv[0]))[0]

    async def series_summary(self, *, commitment_id: UUID) -> dict | None:
        """O que a série tem hoje — para a tela poder avisar antes de criar ou apagar em bloco."""
        dados = await self._series_rows(commitment_id)
        if dados is None:
            return None
        atual, irmas = dados
        referencia = atual.starts_at
        daqui = [
            o for o in irmas
            if referencia is None or o.starts_at is None or o.starts_at >= referencia
        ]
        com_conteudo = 0
        for o in daqui:
            itens = await self.db.scalar(
                select(func.count())
                .select_from(ProjectCommitmentOccurrence)
                .where(ProjectCommitmentOccurrence.meeting_id == o.id)
            )
            anexos = await self.db.scalar(
                select(func.count())
                .select_from(ProjectCommitmentAttachment)
                .where(ProjectCommitmentAttachment.commitment_id == o.id)
            )
            if (itens or 0) + (anexos or 0) > 0:
                com_conteudo += 1
        return {
            "series_id": atual.series_id,
            "every_weeks": self._cadencia_semanas(irmas),
            "total": len(irmas),
            "from_here": len(daqui),
            "from_here_with_content": com_conteudo,
            "last_starts_at": max((o.starts_at for o in irmas if o.starts_at), default=None),
        }

    async def extend_series(
        self, *, commitment_id: UUID, count: int, actor_id: UUID | None
    ) -> list[ProjectCommitment]:
        """Acrescenta N ocorrências ao fim de uma série já criada.

        Errar o número de semanas na criação é o normal (o ciclo muda, entra um mês a mais). Sem
        isto a saída seria cadastrar a reunião solta, e ela nasceria FORA da série — perdendo o
        atalho de levar um item "para a próxima".

        As novas nascem do RITMO da série (primeira ocorrência + múltiplos do intervalo), não da
        data da última: se uma quarta foi remarcada para quinta em caráter de exceção, as
        próximas continuam caindo na quarta.
        """
        if count < 1:
            raise HTTPException(status_code=400, detail="Informe quantas ocorrências acrescentar.")
        dados = await self._series_rows(commitment_id)
        if dados is None:
            raise HTTPException(
                status_code=400, detail="Este compromisso não faz parte de uma repetição."
            )
        _, irmas = dados
        com_data = [o for o in irmas if o.starts_at]
        if not com_data:
            raise HTTPException(status_code=400, detail="A série não tem data para continuar.")
        if len(irmas) + count > self.MAX_OCCURRENCES:
            raise HTTPException(
                status_code=400,
                detail=f"A série chega no limite de {self.MAX_OCCURRENCES} ocorrências.",
            )

        semanas = self._cadencia_semanas(irmas)
        primeira, ultima = com_data[0], com_data[-1]
        # Primeiro múltiplo do ritmo que cai DEPOIS da última ocorrência: é onde a série continua.
        passo = 1
        while primeira.starts_at + timedelta(weeks=semanas * passo) <= ultima.starts_at:
            passo += 1

        # O molde é a última ocorrência: se o local ou os participantes mudaram no meio do
        # caminho, é a configuração mais recente que deve seguir adiante.
        participantes = [p.user_id for p in ultima.participants]
        base = {
            "kind": ultima.kind,
            "title": ultima.title,
            "description": ultima.description,
            "all_day": ultima.all_day,
            "duration_minutes": ultima.duration_minutes,
            "location": ultima.location,
            "modality": ultima.modality,
            "project_id": ultima.project_id,
            "owner_user_id": ultima.owner_user_id,
            "external_participants": ultima.external_participants,
            "series_id": ultima.series_id,
            "participant_ids": participantes,
        }
        folga = (ultima.due_at - ultima.starts_at) if ultima.due_at else None
        criadas: list[ProjectCommitment] = []
        for i in range(count):
            quando = primeira.starts_at + timedelta(weeks=semanas * (passo + i))
            criadas.append(
                await self.create(
                    data={**base, "starts_at": quando, "due_at": (quando + folga) if folga else None},
                    actor_id=actor_id,
                )
            )
        return criadas

    async def delete_series_from(self, *, commitment_id: UUID) -> int:
        """Apaga ESTA ocorrência e as seguintes da mesma série. As passadas ficam.

        Encerrar uma reunião recorrente é dizer "não acontece mais", nunca "nunca aconteceu": o
        que já foi realizado tem ata e pauta e é histórico. Por isso o corte é sempre daqui para
        frente, e a tela avisa quantas das que vão sumir já têm conteúdo.
        """
        dados = await self._series_rows(commitment_id)
        if dados is None:
            raise HTTPException(
                status_code=400, detail="Este compromisso não faz parte de uma repetição."
            )
        atual, irmas = dados
        referencia = atual.starts_at
        apagadas = 0
        for o in irmas:
            if referencia is not None and o.starts_at is not None and o.starts_at < referencia:
                continue
            if await self.delete(commitment_id=o.id):
                apagadas += 1
        return apagadas


def _meeting_date(meeting) -> date | None:
    if meeting is None:
        return None
    quando = meeting.starts_at or meeting.due_at
    return quando.date() if quando else None
