"""Jurídico — eventos (agenda), timeline de fatos e papéis por processo.

Sprint 0 do Workspace Jurídico. As três tabelas são estruturas da Fase 0/1 já aprovadas em
`docs/JURIDICO_ESPECIFICACAO.md`; nenhuma é provisória:

* `legal_events`    — compromissos com data (M4): audiência, perícia, prazo, reunião, diligência.
                      Adiamento preserva o histórico (O7): o evento adiado aponta o novo.
* `legal_timeline`  — fatos consumados (M3), append-only, com procedência e autor (M10).
                      A entrada aponta o fato de origem (`ref_type`/`ref_id`) — a timeline é
                      projeção, nunca a fonte.
* `legal_case_assignments` — papéis datados. Sem isso não existe "precisa de dono" (O3).

PONTE PARA A FASE 0: as três referenciam o PROCESSO (`legal_cases`), que é a unidade que existe
hoje. Quando o Caso (`legal_matters`) nascer como raiz do agregado, a evolução é ADITIVA —
acrescenta `matter_id` e faz backfill a partir do processo. Nada aqui é descartado.

Migration puramente aditiva: nenhuma tabela existente é alterada.

Revision ID: 0120_legal_events_timeline_assignments
Revises: 0119_payable_snapshot_text_columns
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0120_legal_events_timeline_assignments"
down_revision = "0119_payable_snapshot_text_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "legal_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("legal_cases.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column("event_type", sa.String(32), nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="AGENDADO", index=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("modality", sa.String(16), nullable=True),
        sa.Column("responsible_user_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=True),
        # Adiamento preserva histórico: o evento antigo aponta o novo (O7).
        sa.Column(
            "rescheduled_to_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("legal_events.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source", sa.String(24), nullable=False, server_default="MANUAL"),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    op.create_table(
        "legal_timeline",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("legal_cases.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("entry_type", sa.String(32), nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        # A timeline é PROJEÇÃO: aponta o fato de origem, nunca o substitui.
        sa.Column("ref_type", sa.String(32), nullable=True),
        sa.Column("ref_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(24), nullable=False, server_default="MANUAL"),
        sa.Column("is_milestone", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_legal_timeline_case_occurred", "legal_timeline", ["case_id", "occurred_at"])

    op.create_table(
        "legal_case_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("legal_cases.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("role", sa.String(32), nullable=False, index=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("person_name", sa.String(255), nullable=True),
        sa.Column("started_at", sa.Date(), nullable=True),
        sa.Column("ended_at", sa.Date(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    # Backfill da timeline: UMA entrada por processo, marcando de onde ele veio.
    # M13 — não inventamos histórico que não temos: a data é a da criação do registro e o texto
    # é a última movimentação conhecida, quando existir.
    op.execute(
        """
        INSERT INTO legal_timeline
            (id, created_at, updated_at, case_id, occurred_at, entry_type, title, description,
             source, is_milestone)
        SELECT
            gen_random_uuid(), now(), now(), c.id, c.created_at, 'CARGA_INICIAL',
            'Processo carregado na carga inicial',
            NULLIF(c.last_movement, ''),
            'CARGA_INICIAL', true
        FROM legal_cases c
        """
    )


def downgrade() -> None:
    op.drop_table("legal_case_assignments")
    op.drop_index("ix_legal_timeline_case_occurred", table_name="legal_timeline")
    op.drop_table("legal_timeline")
    op.drop_table("legal_events")
