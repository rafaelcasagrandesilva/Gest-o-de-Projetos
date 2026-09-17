"""Agenda de Projetos: andamentos (linha do tempo) de cada item.

Teste real na reunião gerencial (16/09): observações, palpites e conclusões iam todos para o campo
"Ação" do item, à mão e sem data. Cada registro passa a ser uma linha com tipo (Observação,
Atualização, Conclusão), autor, data e a reunião em que foi dito.

Os textos de conclusão já gravados (`project_commitments.completion_note`) viram o primeiro
andamento do tipo Conclusão de cada item, com a data da conclusão — nada se perde. A coluna antiga
continua existindo (guarda a conclusão vigente).

Aditiva. downgrade remove a tabela (a coluna antiga nunca foi tocada).

Revision ID: 0147_commitment_updates
Revises: 0146_keep_create_delete_for_update_holders
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0147_commitment_updates"
down_revision = "0146_keep_create_delete_for_update_holders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_commitment_updates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("commitment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("meeting_id", postgresql.UUID(as_uuid=True), nullable=True),
        # OBSERVACAO | ATUALIZACAO | CONCLUSAO
        sa.Column("kind", sa.String(16), nullable=False, server_default="OBSERVACAO"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["commitment_id"], ["project_commitments.id"], ondelete="CASCADE"),
        # Apagar a reunião não apaga o que foi dito sobre o item — só perde a referência.
        sa.ForeignKeyConstraint(["meeting_id"], ["project_commitments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_project_commitment_updates_commitment_id", "project_commitment_updates", ["commitment_id"])
    op.create_index("ix_project_commitment_updates_meeting_id", "project_commitment_updates", ["meeting_id"])

    # Conclusões já registradas viram o primeiro andamento do item.
    op.execute(
        """
        INSERT INTO project_commitment_updates (id, commitment_id, meeting_id, kind, body, author_id, created_at, updated_at)
        SELECT gen_random_uuid(), c.id, NULL, 'CONCLUSAO', c.completion_note, NULL,
               COALESCE(c.completed_at, c.updated_at), now()
        FROM project_commitments c
        WHERE c.completion_note IS NOT NULL AND btrim(c.completion_note) <> ''
        """
    )


def downgrade() -> None:
    op.drop_index("ix_project_commitment_updates_meeting_id", table_name="project_commitment_updates")
    op.drop_index("ix_project_commitment_updates_commitment_id", table_name="project_commitment_updates")
    op.drop_table("project_commitment_updates")
