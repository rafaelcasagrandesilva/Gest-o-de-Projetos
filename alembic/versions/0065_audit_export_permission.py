"""permissions: audit.export (exportação do log de auditoria).

Revision ID: 0065_audit_export_permission
Revises: 0064_include_in_dashboard
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
from sqlalchemy import text

revision = "0065_audit_export_permission"
down_revision = "0064_include_in_dashboard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(timezone.utc)
    conn.execute(
        text(
            """
            INSERT INTO permissions (id, created_at, updated_at, name)
            VALUES (gen_random_uuid(), :c, :u, :n)
            ON CONFLICT (name) DO NOTHING
            """
        ),
        {"c": now, "u": now, "n": "audit.export"},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DELETE FROM permissions WHERE name = 'audit.export'"))
