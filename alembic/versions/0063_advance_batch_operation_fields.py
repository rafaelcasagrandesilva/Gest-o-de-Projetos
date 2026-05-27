"""Receivable advance batches: operation fields (type + code).

Revision ID: 0063_advance_batch_operation_fields
Revises: 0062_receivable_advance_batches
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0063_advance_batch_operation_fields"
down_revision = "0062_receivable_advance_batches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "receivable_advance_batches",
        sa.Column("operation_type", sa.String(length=32), nullable=False, server_default="BORDERO"),
    )
    op.add_column(
        "receivable_advance_batches",
        sa.Column("operation_code", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_receivable_advance_batches_operation_type",
        "receivable_advance_batches",
        ["operation_type"],
    )
    op.create_index(
        "ix_receivable_advance_batches_operation_code",
        "receivable_advance_batches",
        ["operation_code"],
    )


def downgrade() -> None:
    op.drop_index("ix_receivable_advance_batches_operation_code", table_name="receivable_advance_batches")
    op.drop_index("ix_receivable_advance_batches_operation_type", table_name="receivable_advance_batches")
    op.drop_column("receivable_advance_batches", "operation_code")
    op.drop_column("receivable_advance_batches", "operation_type")

