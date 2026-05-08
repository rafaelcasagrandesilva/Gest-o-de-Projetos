"""receivable_invoices: rename FINALIZADA -> RECEBIDA

Revision ID: 0031_receivable_status_recebida
Revises: 0030_receivable_anticipation_details
"""

from __future__ import annotations

from alembic import op

revision = "0031_receivable_status_recebida"
down_revision = "0030_receivable_anticipation_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE receivable_invoices
        SET invoice_status = 'RECEBIDA'
        WHERE invoice_status = 'FINALIZADA';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE receivable_invoices
        SET invoice_status = 'FINALIZADA'
        WHERE invoice_status = 'RECEBIDA';
        """
    )

