"""Payable snapshots: amount_paid for partial payments.

Revision ID: 0029_payable_snapshot_amount_paid
Revises: 0028_payable_snapshots
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029_payable_snapshot_amount_paid"
down_revision = "0028_payable_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payable_snapshots",
        sa.Column("amount_paid", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0"),
    )
    op.execute(
        """
        UPDATE payable_snapshots
        SET amount_paid = amount_final
        WHERE paid IS TRUE;
        """
    )


def downgrade() -> None:
    op.drop_column("payable_snapshots", "amount_paid")
