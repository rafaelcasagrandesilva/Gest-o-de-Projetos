"""Contratos da Agenda do workspace Projetos.

Vocabulário PRÓPRIO — nenhuma opção vem do Jurídico (decisão de produto: as duas agendas não
compartilham dado nem vocabulário). Ver docs/ETAPA0_AGENDA_PROJETOS.md.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

CommitmentKindLiteral = Literal["REUNIAO", "OBRIGACAO", "EVENTO", "VISITA", "ASSUNTO"]
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
    #: Responsável PRINCIPAL (o primeiro). `owners` traz todos; `owner_name` junta os nomes.
    owner_user_id: UUID | None = None
    owner_name: str | None = None
    owners: list[CommitmentParticipantRead] = Field(default_factory=list)
    #: Obrigação de um item de pauta: o item (ASSUNTO) a que pertence.
    parent_id: UUID | None = None
    parent_title: str | None = None
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
    #: Vários responsáveis (divide a obrigação). Tem precedência sobre `owner_user_id`.
    owner_ids: list[UUID] | None = None
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
    owner_ids: list[UUID] | None = None
    participant_ids: list[UUID] | None = None
    external_participants: str | None = Field(default=None, max_length=500)
    status: CommitmentStatusLiteral | None = None


class CommitmentComplete(BaseModel):
    completion_note: str | None = Field(default=None, max_length=5000)
    #: Reunião em que foi concluída (o histórico diz onde).
    meeting_id: UUID | None = None


class CommitmentReschedule(BaseModel):
    """Alterar o prazo de uma obrigação: novo prazo e, se quiser, o motivo."""

    due_at: datetime
    reason: str | None = Field(default=None, max_length=1000)
    meeting_id: UUID | None = None


class ObligationCreate(BaseModel):
    """Obrigação de um item de pauta: o que fazer, quem (um ou mais) e até quando."""

    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    owner_ids: list[UUID] = Field(default_factory=list)
    due_at: datetime | None = None


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


CommitmentUpdateKindLiteral = Literal["OBSERVACAO", "ATUALIZACAO", "CONCLUSAO", "PRAZO"]


class CommitmentUpdateRead(BaseModel):
    """Andamento de um item (linha do tempo)."""

    id: UUID
    commitment_id: UUID
    kind: CommitmentUpdateKindLiteral
    body: str
    author_id: UUID | None = None
    author_name: str | None = None
    #: Reunião em que foi dito, quando foi.
    meeting_id: UUID | None = None
    meeting_date: date | None = None
    created_at: datetime


class CommitmentUpdateCreate(BaseModel):
    kind: Literal["OBSERVACAO", "ATUALIZACAO"]
    body: str = Field(min_length=1, max_length=5000)
    meeting_id: UUID | None = None


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
    #: Andamentos do item (todas as reuniões) e o mais recente, para a pauta mostrar sem abrir.
    updates_count: int = 0
    last_update: CommitmentUpdateRead | None = None
    #: Resumo das obrigações do item (é o que a linha da pauta mostra).
    obligations_total: int = 0
    obligations_open: int = 0
    obligations_overdue: int = 0


class AgendaItemCreate(BaseModel):
    """Um item de pauta: o assunto, os envolvidos e (opcional) a primeira obrigação."""

    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    external_participants: str | None = Field(default=None, max_length=500)
    project_id: UUID | None = None
    first_obligation: ObligationCreate | None = None


class AgendaItemOutcome(BaseModel):
    outcome: CommitmentOutcomeLiteral
    #: Obrigatório quando `outcome` é EXTENDED: para qual reunião o item foi levado.
    next_meeting_id: UUID | None = None
    #: Texto da caixa: DONE = o que gerou a conclusão; PARTIAL/EXTENDED = o que avançou/falta.
    #: Vira um andamento do item nesta reunião.
    note: str | None = Field(default=None, max_length=5000)
    #: DONE: conclui junto as obrigações ainda em aberto do item.
    complete_obligations: bool = False


class AgendaItemLink(BaseModel):
    """Leva um compromisso que já existe para a pauta de uma reunião."""

    commitment_id: UUID


class MeetingOptionRead(BaseModel):
    """Reunião futura, para escolher o destino de um item estendido."""

    id: UUID
    title: str
    starts_at: datetime | None = None
    #: Permite destacar a próxima ocorrência da MESMA série na hora de levar um item adiante.
    series_id: UUID | None = None


class SeriesSummaryRead(BaseModel):
    """Estado da repetição, para a tela avisar antes de acrescentar ou apagar em bloco."""

    series_id: UUID
    every_weeks: int
    total: int
    #: Desta ocorrência em diante — o que um "excluir a série" levaria junto.
    from_here: int
    #: Quantas dessas já têm ata anexada ou item de pauta: apagar aí destrói registro.
    from_here_with_content: int
    last_starts_at: datetime | None = None


class SeriesExtend(BaseModel):
    """Quantas ocorrências acrescentar ao fim da série. O intervalo é o que ela já tem."""

    count: int = Field(ge=1, le=52)
