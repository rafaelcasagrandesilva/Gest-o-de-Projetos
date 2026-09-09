"""Agenda de Projetos: reuniões recorrentes (a gerencial de toda quarta).

`series_id` marca as ocorrências nascidas da mesma repetição. As ocorrências são
**materializadas**: cada quarta-feira é um compromisso de verdade, e não uma data calculada na
hora. É o que permite o que a gestão precisa — cada reunião tem a SUA ata anexada, os seus
participantes e a sua pauta, e mover uma data não mexe nas outras. Uma ocorrência virtual não
guardaria anexo nem pauta própria.

Sem regra de recorrência gravada (RRULE): a série é criada de uma vez, e a partir daí cada
ocorrência vive por conta própria. Isso troca "editar a série inteira" por "editar uma
ocorrência", que é exatamente o comportamento pedido — remarcar uma quarta sem tocar nas demais.

Exclusivamente ADITIVA.

Revision ID: 0132_commitment_series
Revises: 0131_commitment_meeting_occurrences
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0132_commitment_series"
down_revision = "0131_commitment_meeting_occurrences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_commitments", sa.Column("series_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_index("ix_project_commitments_series_id", "project_commitments", ["series_id"])


def downgrade() -> None:
    op.drop_index("ix_project_commitments_series_id", table_name="project_commitments")
    op.drop_column("project_commitments", "series_id")
