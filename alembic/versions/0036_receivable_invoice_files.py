"""receivable invoice files (multi pdf)

Revision ID: 0036_receivable_invoice_files
Revises: 0035_payable_snapshot_anticipation_unique_index
Create Date: 2026-04-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0036_receivable_invoice_files"
down_revision = "0035_payable_snapshot_anticipation_unique_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "receivable_invoice_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("receivable_invoices.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_receivable_invoice_files_invoice_id_created_at",
        "receivable_invoice_files",
        ["invoice_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_receivable_invoice_files_invoice_id_created_at", table_name="receivable_invoice_files")
    op.drop_table("receivable_invoice_files")
