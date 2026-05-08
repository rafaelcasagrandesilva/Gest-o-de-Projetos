"""receivable_invoice_anticipations: received_date

Revision ID: 0046_receivable_anticipation_received_date
Revises: 0045_normalize_revenue_competencia
Create Date: 2026-04-30

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0046_receivable_anticipation_received_date"
down_revision = "0045_normalize_revenue_competencia"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "receivable_invoice_anticipations",
        sa.Column("received_date", sa.Date(), nullable=True),
    )
    op.create_index(
        op.f("ix_receivable_invoice_anticipations_received_date"),
        "receivable_invoice_anticipations",
        ["received_date"],
        unique=False,
    )

    # Backfill: usa a data de criação como aproximação do recebimento (linha de antecipação já representa entrada).
    op.execute(
        sa.text(
            """
            UPDATE receivable_invoice_anticipations
            SET received_date = COALESCE(received_date, created_at::date)
            WHERE received_date IS NULL;
            """
        )
    )
    op.alter_column("receivable_invoice_anticipations", "received_date", nullable=False)


def downgrade() -> None:
    op.drop_index(
        op.f("ix_receivable_invoice_anticipations_received_date"),
        table_name="receivable_invoice_anticipations",
    )
    op.drop_column("receivable_invoice_anticipations", "received_date")

