"""RBAC: add payables.view + receivables.view permissions.

Revision ID: 0025_add_payables_receivables_permissions
Revises: 0024_receivable_simplified
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0025_add_payables_receivables_permissions"
down_revision = "0026_fix_alembic_version_column"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(timezone.utc)

    # Idempotente (não quebra em ambientes onde já exista).
    for code in ("payables.view", "receivables.view"):
        exists = conn.execute(text("SELECT 1 FROM permissions WHERE name = :n"), {"n": code}).fetchone()
        if exists:
            continue
        conn.execute(
            text(
                """
                INSERT INTO permissions (id, created_at, updated_at, name)
                VALUES (gen_random_uuid(), :c, :u, :n)
                """
            ),
            {"c": now, "u": now, "n": code},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DELETE FROM permissions WHERE name IN ('payables.view', 'receivables.view')"))

