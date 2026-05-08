"""Add unique index for anticipation payables snapshot.

Revision ID: 0035_payable_snapshot_anticipation_unique_index
Revises: 0034_invoice_anticipations
Create Date: 2026-04-28

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0035_payable_snapshot_anticipation_unique_index"
down_revision = "0034_invoice_anticipations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_payable_snapshots_antecipacao_month_ref",
        "payable_snapshots",
        ["month", "ref_id"],
        unique=True,
        postgresql_where="type = 'ANTECIPACAO' AND ref_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("uq_payable_snapshots_antecipacao_month_ref", table_name="payable_snapshots")

