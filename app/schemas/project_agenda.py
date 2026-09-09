"""Contratos da Agenda do workspace Projetos.

Vocabulário PRÓPRIO — nenhuma opção vem do Jurídico (decisão de produto: as duas agendas não
compartilham dado nem vocabulário). Ver docs/ETAPA0_AGENDA_PROJETOS.md.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

CommitmentKindLiteral = Literal["REUNIAO", "OBRIGACAO", "EVENTO", "PRAZO", "VISITA"]
CommitmentStatusLiteral = Literal["AGENDADO", "CONCLUIDO", "CANCELADO", "ADIADO"]
CommitmentModalityLiteral = Literal["PRESENCIAL", "VIRTUAL", "HIBRIDA"]


class CommitmentParticipantRead(BaseModel):
    user_id: UUID
    full_name: str


class CommitmentAttachmentRead(BaseModel):
    id: UUID
    file_name: str
    mime_type: str | None = None
    size_bytes: int = 0
    #: Destaca a ATA da reunião entre os demais documentos.
    is_minutes: bool = False
    created_at: datetime


class CommitmentRead(BaseModel):
    id: UUID
    kind: str
    title: str
    description: str | None = None
    starts_at: datetime | None = None
    due_at: datetime | None = None
    all_day: bool = False
    duration_minutes: int | None = None
    location: str | None = None
    modality: str | None = None
    project_id: UUID | None = None
    project_name: str | None = None
    owner_user_id: UUID | None = None
    owner_name: str | None = None
    external_participants: str | None = None
    status: str
    completed_at: datetime | None = None
    completion_note: str | None = None
    #: Ocorrências da mesma repetição (a gerencial de toda quarta).
    series_id: UUID | None = None
    #: Tem prazo, já passou e ninguém fechou. Compromisso sem data nunca atrasa — só espera.
    is_overdue: bool = False
    participants: list[CommitmentParticipantRead] = Field(default_factory=list)
    attachments: list[CommitmentAttachmentRead] = Field(default_factory=list)
    created_by_id: UUID | None = None


class CommitmentCreate(BaseModel):
    kind: CommitmentKindLiteral
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    #: `starts_at` para o que ACONTECE numa hora; `due_at` para o que precisa estar ENTREGUE.
    #: Nenhum dos dois = backlog: aparece na lista, nunca no calendário.
    starts_at: datetime | None = None
    due_at: datetime | None = None
    all_day: bool = False
    duration_minutes: int | None = Field(default=None, ge=0, le=24 * 60)
    location: str | None = Field(default=None, max_length=255)
    modality: CommitmentModalityLiteral | None = None
    project_id: UUID | None = None
    #: Opcional: numa reunião o responsável é quem convocou, e nem sempre há um.
    owner_user_id: UUID | None = None
    participant_ids: list[UUID] = Field(default_factory=list)
    #: Quem não tem login (escritório, cliente, colaborador sem acesso).
    external_participants: str | None = Field(default=None, max_length=500)
    #: Repetição: a cada quantas semanas e por quantas ocorrências. Ausente = compromisso único.
    repeat_every_weeks: int | None = Field(default=None, ge=1, le=8)
    repeat_count: int | None = Field(default=None, ge=2, le=52)


class CommitmentUpdate(BaseModel):
    kind: CommitmentKindLiteral | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    starts_at: datetime | None = None
    due_at: datetime | None = None
    all_day: bool | None = None
    duration_minutes: int | None = Field(default=None, ge=0, le=24 * 60)
    location: str | None = Field(default=None, max_length=255)
    modality: CommitmentModalityLiteral | None = None
    project_id: UUID | None = None
    owner_user_id: UUID | None = None
    participant_ids: list[UUID] | None = None
    external_participants: str | None = Field(default=None, max_length=500)
    status: CommitmentStatusLiteral | None = None


class CommitmentComplete(BaseModel):
    completion_note: str | None = None


class AgendaCountersRead(BaseModel):
    """Atrasados e desta semana — no total e os meus. É o que transforma o registro em cobrança."""

    overdue: int
    overdue_mine: int
    this_week: int
    this_week_mine: int


class AgendaUserRead(BaseModel):
    """Usuário selecionável como responsável/participante."""

    id: UUID
    full_name: str


# --- pauta da reunião: o item e o desfecho DELE naquela reunião ---------------------------

CommitmentOutcomeLiteral = Literal["OPEN", "DONE", "PARTIAL", "EXTENDED"]


class AgendaItemRead(CommitmentRead):
    """Um item em pauta: o compromisso + o que aconteceu com ele NAQUELA reunião."""

    occurrence_id: UUID
    outcome: str
    #: 1 = nasceu nesta reunião; 2+ = veio estendido de uma anterior.
    occurrence_number: int
    total_occurrences: int
    extended_to_meeting_id: UUID | None = None
    extended_to_date: date | None = None
    came_from_date: date | None = None


class AgendaItemCreate(BaseModel):
    """Uma linha da ata: assunto, ação, envolvidos, responsável e prazo."""

    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    due_at: datetime | None = None
    owner_user_id: UUID | None = None
    external_participants: str | None = Field(default=None, max_length=500)
    project_id: UUID | None = None


class AgendaItemOutcome(BaseModel):
    outcome: CommitmentOutcomeLiteral
    #: Obrigatório quando `outcome` é EXTENDED: para qual reunião o item foi levado.
    next_meeting_id: UUID | None = None


class MeetingOptionRead(BaseModel):
    """Reunião futura, para escolher o destino de um item estendido."""

    id: UUID
    title: str
    starts_at: datetime | None = None
    #: Permite destacar a próxima ocorrência da MESMA série na hora de levar um item adiante.
    series_id: UUID | None = None
