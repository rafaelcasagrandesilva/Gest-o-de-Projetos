"""Operação de antecipação: data de confirmação.

Adiciona `confirmed_at` (timestamp) em `receivable_advance_batches`, registrado no
momento da confirmação (DRAFT → OPEN). NULL para rascunhos e operações legadas.

Revision ID: 0077_advance_batch_confirmed_at
Revises: 0076_advance_expected_actual
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0077_advance_batch_confirmed_at"
down_revision = "0076_advance_expected_actual"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "receivable_advance_batches",
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("receivable_advance_batches", "confirmed_at")
