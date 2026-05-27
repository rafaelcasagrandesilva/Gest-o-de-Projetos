"""Ledger de pagamentos de contas a pagar (eventos de caixa).

Revision ID: 0059_payable_payments
Revises: 0058_cost_center_aliases
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0059_payable_payments"
down_revision = "0058_cost_center_aliases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payable_payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payable_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversal_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["payable_snapshot_id"], ["payable_snapshots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payable_payments_payable_snapshot_id", "payable_payments", ["payable_snapshot_id"])
    op.create_index("ix_payable_payments_payment_date", "payable_payments", ["payment_date"])
    op.create_index("ix_payable_payments_reversed_at", "payable_payments", ["reversed_at"])

    # Backfill: um evento sintético por snapshot já pago (preserva amount_paid e histórico).
    op.execute(
        """
        INSERT INTO payable_payments (
            id, created_at, updated_at, payable_snapshot_id, amount, payment_date,
            observation, created_by, reversed_at, reversal_reason
        )
        SELECT
            gen_random_uuid(),
            COALESCE(ps.updated_at, ps.created_at, NOW()),
            COALESCE(ps.updated_at, ps.created_at, NOW()),
            ps.id,
            ps.amount_paid,
            COALESCE(ps.payment_date, ps.due_date, ps.month),
            '[migração] pagamento histórico consolidado',
            NULL,
            NULL,
            NULL
        FROM payable_snapshots ps
        WHERE ps.amount_paid > 0
          AND NOT EXISTS (
              SELECT 1 FROM payable_payments pp WHERE pp.payable_snapshot_id = ps.id
          );
        """
    )


def downgrade() -> None:
    op.drop_index("ix_payable_payments_reversed_at", table_name="payable_payments")
    op.drop_index("ix_payable_payments_payment_date", table_name="payable_payments")
    op.drop_index("ix_payable_payments_payable_snapshot_id", table_name="payable_payments")
    op.drop_table("payable_payments")
