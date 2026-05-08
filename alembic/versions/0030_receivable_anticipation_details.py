"""receivable_invoices: add anticipation financial fields

Revision ID: 0030_receivable_anticipation_details
Revises: 0029_payable_snapshot_amount_paid
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030_receivable_anticipation_details"
down_revision = "0029_payable_snapshot_amount_paid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "receivable_invoices",
        sa.Column("advance_amount_received", sa.Numeric(14, 2), nullable=True),
    )
    op.add_column(
        "receivable_invoices",
        sa.Column("advance_amount_due", sa.Numeric(14, 2), nullable=True),
    )
    op.add_column(
        "receivable_invoices",
        sa.Column("advance_due_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("receivable_invoices", "advance_due_date")
    op.drop_column("receivable_invoices", "advance_amount_due")
    op.drop_column("receivable_invoices", "advance_amount_received")

