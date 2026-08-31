"""Jurídico — operação: eventos (agenda), timeline de fatos e papéis.

Segue `docs/JURIDICO_PRINCIPIOS.md`:

* **M3** — a timeline registra apenas fatos consumados, com data de ocorrência, autor e origem.
* **M4** — a agenda registra apenas compromissos; ao acontecer, o evento VIRA fato.
* **M9/O7** — nada se apaga: evento adiado aponta o novo, e a correção é fato novo.
* **M10** — todo fato tem procedência.
* **O3** — trabalho sem dono não existe; daí os papéis por processo.

Ponte para a Fase 0: hoje tudo referencia o PROCESSO (`legal_cases`). Quando o Caso
(`legal_matters`) nascer como raiz, a evolução é aditiva — acrescenta `matter_id`.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampUUIDMixin


class LegalEventType(str, enum.Enum):
    """Tudo o que tem data. A agenda é uma VISUALIZAÇÃO destes registros, não uma entidade."""

    AUDIENCIA = "AUDIENCIA"
    PERICIA = "PERICIA"
    SESSAO_ARBITRAL = "SESSAO_ARBITRAL"
    REUNIAO = "REUNIAO"
    PRAZO_PROCESSUAL = "PRAZO_PROCESSUAL"
    PRAZO_INTERNO = "PRAZO_INTERNO"
    DILIGENCIA = "DILIGENCIA"
    OUTRO = "OUTRO"


class LegalEventStatus(str, enum.Enum):
    AGENDADO = "AGENDADO"
    REALIZADO = "REALIZADO"
    CUMPRIDO = "CUMPRIDO"
    ADIADO = "ADIADO"
    CANCELADO = "CANCELADO"
    NAO_COMPARECIDO = "NAO_COMPARECIDO"


class LegalEventModality(str, enum.Enum):
    PRESENCIAL = "PRESENCIAL"
    VIRTUAL = "VIRTUAL"
    HIBRIDA = "HIBRIDA"


class LegalTimelineEntryType(str, enum.Enum):
    """Naturezas de FATO. Nunca inclui compromisso futuro — esse mora na agenda (M4)."""

    CARGA_INICIAL = "CARGA_INICIAL"
    ANDAMENTO = "ANDAMENTO"
    EVENTO_REALIZADO = "EVENTO_REALIZADO"
    MUDANCA_ESTADO = "MUDANCA_ESTADO"
    DOCUMENTO = "DOCUMENTO"
    NOTA = "NOTA"
    FINANCEIRO = "FINANCEIRO"
    BLOQUEIO = "BLOQUEIO"


class LegalFactSource(str, enum.Enum):
    """Procedência (M10): permite confiar em números mistos e conviver com automação futura."""

    MANUAL = "MANUAL"
    CARGA_INICIAL = "CARGA_INICIAL"
    PUBLICACAO = "PUBLICACAO"
    INTEGRACAO = "INTEGRACAO"
    SISTEMA = "SISTEMA"


class LegalAssignmentRole(str, enum.Enum):
    RESPONSAVEL_JURIDICO = "RESPONSAVEL_JURIDICO"
    RESPONSAVEL_OPERACIONAL = "RESPONSAVEL_OPERACIONAL"
    ADVOGADO_EXTERNO = "ADVOGADO_EXTERNO"
    ESCRITORIO = "ESCRITORIO"


class LegalEvent(TimestampUUIDMixin, Base):
    """Compromisso com data. Ao ser concluído, gera o fato correspondente na timeline."""

    __tablename__ = "legal_events"

    case_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("legal_cases.id", ondelete="CASCADE"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # Nulo = compromisso sem data marcada (backlog): aparece na lista, não no calendário.
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=LegalEventStatus.AGENDADO.value, index=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    modality: Mapped[str | None] = mapped_column(String(16), nullable=True)
    responsible_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    # O7: remarcar não apaga — o evento antigo fica ADIADO apontando o novo.
    rescheduled_to_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("legal_events.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(24), nullable=False, default=LegalFactSource.MANUAL.value)
    created_by_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)


class LegalTimelineEntry(TimestampUUIDMixin, Base):
    """Fato consumado. Append-only: corrigir é registrar um fato novo (O6)."""

    __tablename__ = "legal_timeline"

    case_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("legal_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Quando o fato OCORREU — não quando foi digitado (`created_at` guarda isso).
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # M12/M3: a entrada aponta o fato de origem; ela é projeção, não a fonte da verdade.
    ref_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ref_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    source: Mapped[str] = mapped_column(String(24), nullable=False, default=LegalFactSource.MANUAL.value)
    is_milestone: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)


class LegalCaseAssignment(TimestampUUIDMixin, Base):
    """Papel datado no processo. Caso ativo sem responsável jurídico é alerta (O3)."""

    __tablename__ = "legal_case_assignments"

    case_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("legal_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    # Para quem não é usuário do SGC (advogado externo, escritório).
    person_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    ended_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
