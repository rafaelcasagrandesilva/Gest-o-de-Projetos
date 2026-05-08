"""add pix key to employees

Revision ID: 0037_add_employee_pix_key
Revises: 0036_receivable_invoice_files
Create Date: 2026-04-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0037_add_employee_pix_key"
down_revision = "0036_receivable_invoice_files"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("pix_key_type", sa.String(length=32), nullable=True))
    op.add_column("employees", sa.Column("pix_key", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("employees", "pix_key")
    op.drop_column("employees", "pix_key_type")

