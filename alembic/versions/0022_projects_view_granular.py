"""permissions: projects.view_list e projects.view_detail (granularidade futura).

Revision ID: 0022_projects_view_granular
Revises: 0021_audit_logs_production
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0022_projects_view_granular"
down_revision = "0021_audit_logs_production"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(timezone.utc)
    for name in ("projects.view_list", "projects.view_detail"):
        conn.execute(
            text(
                """
                INSERT INTO permissions (id, created_at, updated_at, name)
                SELECT gen_random_uuid(), :c, :u, :n
                WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE name = :n)
                """
            ),
            {"c": now, "u": now, "n": name},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DELETE FROM permissions WHERE name IN ('projects.view_list', 'projects.view_detail')"))
