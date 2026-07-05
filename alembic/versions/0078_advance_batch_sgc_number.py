"""Operação de antecipação: número interno sequencial do SGC.

Adiciona `sgc_number` (inteiro) em `receivable_advance_batches`: identificador
operacional interno, sequência global simples (1, 2, 3, …), única e imutável.
Independente do `batch_number` técnico (BT-...) e do `operation_code` (número da
instituição). Backfill determinístico das operações existentes por (created_at, id).

Revision ID: 0078_advance_batch_sgc_number
Revises: 0077_advance_batch_confirmed_at
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0078_advance_batch_sgc_number"
down_revision = "0077_advance_batch_confirmed_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Coluna nullable para permitir o backfill.
    op.add_column(
        "receivable_advance_batches",
        sa.Column("sgc_number", sa.BigInteger(), nullable=True),
    )

    # 2. Backfill: 1, 2, 3, … por ordem de criação (empate → id, determinístico).
    op.execute(
        """
        WITH ordered AS (
            SELECT id,
                   ROW_NUMBER() OVER (ORDER BY created_at ASC, id ASC) AS seq
            FROM receivable_advance_batches
        )
        UPDATE receivable_advance_batches AS b
        SET sgc_number = ordered.seq
        FROM ordered
        WHERE b.id = ordered.id
        """
    )

    # 3. Torna NOT NULL + UNIQUE + índice.
    op.alter_column("receivable_advance_batches", "sgc_number", nullable=False)
    op.create_unique_constraint(
        "uq_receivable_advance_batches_sgc_number",
        "receivable_advance_batches",
        ["sgc_number"],
    )
    op.create_index(
        "ix_receivable_advance_batches_sgc_number",
        "receivable_advance_batches",
        ["sgc_number"],
    )


def downgrade() -> None:
    op.drop_index("ix_receivable_advance_batches_sgc_number", table_name="receivable_advance_batches")
    op.drop_constraint(
        "uq_receivable_advance_batches_sgc_number",
        "receivable_advance_batches",
        type_="unique",
    )
    op.drop_column("receivable_advance_batches", "sgc_number")
