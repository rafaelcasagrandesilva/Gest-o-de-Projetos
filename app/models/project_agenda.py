from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin


class CommitmentKind(str, enum.Enum):
    """Naturezas da agenda de PROJETOS — deliberadamente próprias.

    Nada aqui conversa com `LegalEventType` (Audiência, Perícia, Sessão Arbitral): decisão de
    produto de que as duas agendas não compartilham dado nem vocabulário. Ver
    docs/ETAPA0_AGENDA_PROJETOS.md.
    """

    REUNIAO = "REUNIAO"
    OBRIGACAO = "OBRIGACAO"
    EVENTO = "EVENTO"
    PRAZO = "PRAZO"
    VISITA = "VISITA"


class CommitmentStatus(str, enum.Enum):
    AGENDADO = "AGENDADO"
    CONCLUIDO = "CONCLUIDO"
    CANCELADO = "CANCELADO"
    ADIADO = "ADIADO"


class CommitmentModality(str, enum.Enum):
    PRESENCIAL = "PRESENCIAL"
    VIRTUAL = "VIRTUAL"
    HIBRIDA = "HIBRIDA"


class ProjectCommitment(TimestampUUIDMixin, Base):
    """Um compromisso da agenda de Projetos: reunião, obrigação atribuída, evento, prazo ou visita.

    Um registro só atende os dois usos que motivaram o módulo, porque o que os une é **data,
    gente e cobrança**:

    - *obrigação* — "João traz a resposta da Vilela até sexta": `owner_user_id` + `due_at` +
      `description`;
    - *reunião* — "quarta, gestores, 10h": `starts_at` + `location` + participantes + a ata
      anexada depois.

    `owner_user_id` é OPCIONAL por decisão do usuário: numa reunião o responsável é quem
    convocou, e nem sempre há um.
    """

    __tablename__ = "project_commitments"

    kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Um dos dois basta: `starts_at` para o que ACONTECE numa hora (reunião, visita);
    # `due_at` para o que precisa estar ENTREGUE até uma data (obrigação, prazo).
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    all_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    modality: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Projeto relacionado é OPCIONAL: uma reunião de gestores pode não ser de projeto nenhum.
    project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Responsável: quem responde pela entrega. Opcional (ver docstring da classe).
    owner_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Quem não tem login (escritório, cliente, colaborador sem acesso). Texto livre de propósito:
    # inventar cadastro de contato para isso seria custo sem uso.
    external_participants: Mapped[str | None] = mapped_column(String(500), nullable=True)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CommitmentStatus.AGENDADO.value, server_default="AGENDADO", index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completion_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    participants: Mapped[list["ProjectCommitmentParticipant"]] = relationship(
        back_populates="commitment", cascade="all, delete-orphan"
    )
    attachments: Mapped[list["ProjectCommitmentAttachment"]] = relationship(
        back_populates="commitment", cascade="all, delete-orphan"
    )


class ProjectCommitmentParticipant(TimestampUUIDMixin, Base):
    """Quem participa do compromisso. O responsável entra aqui também, pelo serviço."""

    __tablename__ = "project_commitment_participants"
    __table_args__ = (
        UniqueConstraint("commitment_id", "user_id", name="uq_project_commitment_participant"),
    )

    commitment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("project_commitments.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    commitment: Mapped["ProjectCommitment"] = relationship(back_populates="participants")


class ProjectCommitmentAttachment(TimestampUUIDMixin, Base):
    """Anexo do compromisso — a ATA da reunião, hoje feita fora e anexada aqui.

    Só metadados no banco; o arquivo mora no volume sob `STORAGE_ROOT`, como os PDFs de NF e os
    comprovantes de reembolso. Quando o sistema passar a gerar a ata sozinho, ela nasce como mais
    um registro desta tabela — o modelo não muda.
    """

    __tablename__ = "project_commitment_attachments"

    commitment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("project_commitments.id", ondelete="CASCADE"), index=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Distingue a ATA dos demais documentos sem inventar tabela: a tela destaca a ata.
    is_minutes: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    uploaded_by_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    commitment: Mapped["ProjectCommitment"] = relationship(back_populates="attachments")


class CommitmentOutcome(str, enum.Enum):
    """Desfecho de um item NAQUELA reunião — o ritmo da reunião gerencial semanal."""

    OPEN = "OPEN"
    DONE = "DONE"
    PARTIAL = "PARTIAL"
    EXTENDED = "EXTENDED"


class ProjectCommitmentOccurrence(TimestampUUIDMixin, Base):
    """A passagem de um item por uma reunião.

    Um mesmo assunto costuma ser tratado em várias reuniões seguidas, com desfecho diferente em
    cada uma. Guardar o desfecho no item daria só o último, e a ata de cada reunião perderia o
    registro do que foi decidido nela. Uma linha por (item × reunião) preserva as duas leituras:
    a reunião de 03/09 continua mostrando "estendido para 10/09", e "esse assunto já rolou 4
    vezes" vira uma contagem.

    `commitment_id` e `meeting_id` apontam para a MESMA tabela: tanto o item quanto a reunião são
    compromissos. É o que permite ao item herdar calendário, prazo e "só os meus" de graça.
    """

    __tablename__ = "project_commitment_occurrences"
    __table_args__ = (
        UniqueConstraint("commitment_id", "meeting_id", name="uq_commitment_occurrence"),
    )

    commitment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("project_commitments.id", ondelete="CASCADE"), index=True
    )
    meeting_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("project_commitments.id", ondelete="CASCADE"), index=True
    )
    outcome: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CommitmentOutcome.OPEN.value, server_default="OPEN"
    )
