"""Agenda de Projetos: item de pauta vira ASSUNTO com OBRIGAÇÕES filhas (vários responsáveis).

Teste na gerencial (17/09): um item com uma "Ação" única e um responsável não dava conta — cada
assunto gera várias obrigações, às vezes de pessoas diferentes, e a pauta ficava ilegível.

Modelo novo:
- `project_commitments.parent_id`: a obrigação aponta para o item de pauta (kind `ASSUNTO`);
- `project_commitment_participants.is_owner`: os RESPONSÁVEIS são participantes marcados (pode haver
  mais de um) — o "só os meus" e os contadores já olham os participantes;
- o ASSUNTO não tem responsável nem prazo e sai do calendário; quem cobra são as obrigações.

Conversão dos itens que já estão em pauta (todo compromisso não-reunião com passagem por reunião):
cada um vira ASSUNTO e ganha UMA obrigação filha com o que ele tinha — texto da "Ação", responsável,
prazo, situação e observação de conclusão. O título da obrigação é a primeira linha da ação (ou o
título do item, se não havia ação). Nada se perde; os andamentos continuam no assunto.

VALIDAÇÃO: todo item convertido ganha exatamente uma obrigação; senão aborta.
downgrade: remove as colunas (as obrigações criadas ficariam como compromissos soltos — por isso o
downgrade as apaga e devolve o kind OBRIGACAO aos assuntos; responsável/prazo não voltam).

Revision ID: 0148_agenda_item_obligations
Revises: 0147_commitment_updates
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0148_agenda_item_obligations"
down_revision = "0147_commitment_updates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_commitments", sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_project_commitments_parent_id", "project_commitments", "project_commitments",
        ["parent_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_project_commitments_parent_id", "project_commitments", ["parent_id"])
    op.add_column(
        "project_commitment_participants",
        sa.Column("is_owner", sa.Boolean(), nullable=False, server_default="false"),
    )

    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE project_commitment_participants p SET is_owner = true
        FROM project_commitments c
        WHERE c.id = p.commitment_id AND c.owner_user_id = p.user_id
    """))

    itens = [r[0] for r in conn.execute(sa.text("""
        SELECT DISTINCT c.id FROM project_commitments c
        JOIN project_commitment_occurrences o ON o.commitment_id = c.id
        WHERE c.kind <> 'REUNIAO'
    """)).all()]

    for item_id in itens:
        filho = conn.execute(sa.text("""
            INSERT INTO project_commitments (
                id, created_at, updated_at, kind, title, description, starts_at, due_at, all_day,
                duration_minutes, location, modality, project_id, owner_user_id, external_participants,
                status, completed_at, completion_note, created_by_id, series_id, parent_id
            )
            SELECT gen_random_uuid(), c.created_at, now(), 'OBRIGACAO',
                   CASE WHEN btrim(coalesce(c.description, '')) <> ''
                        THEN left(btrim(split_part(btrim(c.description), E'\\n', 1)), 255)
                        ELSE c.title END,
                   CASE WHEN btrim(coalesce(c.description, '')) <> ''
                         AND (position(E'\\n' in btrim(c.description)) > 0 OR length(btrim(c.description)) > 255)
                        THEN c.description ELSE NULL END,
                   NULL, c.due_at, false, NULL, NULL, NULL, c.project_id, c.owner_user_id, NULL,
                   c.status, c.completed_at, c.completion_note, c.created_by_id, NULL, c.id
            FROM project_commitments c WHERE c.id = :id
            RETURNING id
        """), {"id": item_id}).scalar_one()
        # O responsável do item passa para a obrigação.
        conn.execute(sa.text("""
            INSERT INTO project_commitment_participants (id, created_at, updated_at, commitment_id, user_id, is_owner)
            SELECT gen_random_uuid(), now(), now(), :filho, c.owner_user_id, true
            FROM project_commitments c WHERE c.id = :id AND c.owner_user_id IS NOT NULL
        """), {"filho": filho, "id": item_id})
        conn.execute(sa.text("""
            DELETE FROM project_commitment_participants p
            USING project_commitments c
            WHERE c.id = p.commitment_id AND c.id = :id AND p.user_id = c.owner_user_id
        """), {"id": item_id})
        conn.execute(sa.text("""
            UPDATE project_commitments
            SET kind = 'ASSUNTO', owner_user_id = NULL, due_at = NULL, starts_at = NULL,
                completion_note = NULL, updated_at = now()
            WHERE id = :id
        """), {"id": item_id})

    # A coluna acabou de nascer: toda obrigação com pai foi criada aqui.
    filhos = conn.execute(sa.text(
        "SELECT count(DISTINCT parent_id) FROM project_commitments WHERE parent_id IS NOT NULL"
    )).scalar_one()
    if filhos != len(itens):
        raise RuntimeError(f"0148: {len(itens)} itens convertidos, mas {filhos} obrigações criadas")


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM project_commitments WHERE parent_id IS NOT NULL"))
    conn.execute(sa.text("UPDATE project_commitments SET kind = 'OBRIGACAO' WHERE kind = 'ASSUNTO'"))
    op.drop_column("project_commitment_participants", "is_owner")
    op.drop_index("ix_project_commitments_parent_id", table_name="project_commitments")
    op.drop_constraint("fk_project_commitments_parent_id", "project_commitments", type_="foreignkey")
    op.drop_column("project_commitments", "parent_id")
