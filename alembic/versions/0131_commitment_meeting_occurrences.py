"""Agenda de Projetos: itens de reunião que rolam de uma reunião para a próxima.

Fecha o ciclo que a agenda deixava aberto: a reunião gera ITENS (Assunto · Ação · Envolvidos ·
Responsável · Prazo), e a cada reunião seguinte cada item recebe um desfecho — **Concluído**,
**Parcial** ou **Estendido para a próxima**. É o ritmo da reunião gerencial semanal.

**Por que uma tabela de OCORRÊNCIAS, e não um campo no item:** um mesmo assunto costuma ser
tratado em várias reuniões seguidas, com desfecho diferente em cada uma. Guardar o desfecho no
item daria só o último, e a ata de cada reunião perderia o registro do que foi decidido nela.
Com uma linha por (item × reunião), a reunião de 03/09 continua mostrando "estendido para
10/09", a de 10/09 mostra o item ativo, e "esse assunto já rolou 4 vezes" é uma contagem.

O ITEM continua sendo um compromisso comum (`project_commitments`), com responsável, prazo e
status — é o que faz ele aparecer no calendário, nos contadores de atraso e no "só os meus".

`follow_up` (devolutiva em texto) foi retirado por decisão do usuário: a devolutiva real é
longa e vive na ATA anexada; no sistema fica o essencial estruturado. O campo chegou a existir
no desenho anterior e nunca foi publicado.

Exclusivamente ADITIVA em relação à 0130.

Revision ID: 0131_commitment_meeting_occurrences
Revises: 0130_project_agenda
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0131_commitment_meeting_occurrences"
down_revision = "0130_project_agenda"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_commitment_occurrences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # O item tratado.
        sa.Column("commitment_id", postgresql.UUID(as_uuid=True), nullable=False),
        # A reunião em que ele entrou em pauta.
        sa.Column("meeting_id", postgresql.UUID(as_uuid=True), nullable=False),
        # OPEN | DONE | PARTIAL | EXTENDED — o desfecho NAQUELA reunião.
        sa.Column("outcome", sa.String(16), nullable=False, server_default="OPEN"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # Apagar o item apaga as passagens dele; apagar a reunião não pode apagar o item, mas a
        # passagem por ela deixa de existir — o item segue vivo nas outras reuniões.
        sa.ForeignKeyConstraint(
            ["commitment_id"], ["project_commitments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["meeting_id"], ["project_commitments.id"], ondelete="CASCADE"),
        # Um item entra uma vez em cada reunião: marcar duas vezes é erro, não histórico.
        sa.UniqueConstraint("commitment_id", "meeting_id", name="uq_commitment_occurrence"),
    )
    op.create_index(
        "ix_project_commitment_occurrences_commitment_id",
        "project_commitment_occurrences",
        ["commitment_id"],
    )
    op.create_index(
        "ix_project_commitment_occurrences_meeting_id",
        "project_commitment_occurrences",
        ["meeting_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_project_commitment_occurrences_meeting_id", table_name="project_commitment_occurrences"
    )
    op.drop_index(
        "ix_project_commitment_occurrences_commitment_id",
        table_name="project_commitment_occurrences",
    )
    op.drop_table("project_commitment_occurrences")
