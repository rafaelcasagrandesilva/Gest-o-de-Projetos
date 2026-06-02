"""include_in_dashboard em lançamentos financeiros (CAP/CAR).

Revision ID: 0064_include_in_dashboard
Revises: 0063_advance_batch_operation_fields
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0064_include_in_dashboard"
down_revision = "0063_advance_batch_operation_fields"
branch_labels = None
depends_on = None

_TABLES = (
    "payable_snapshots",
    "receivable_invoices",
    "receivable_invoice_anticipations",
    "receivable_manual_items",
    "receivable_advance_batches",
)


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "include_in_dashboard",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
        )
    for table in _TABLES:
        op.alter_column(table, "include_in_dashboard", server_default=None)


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_column(table, "include_in_dashboard")
