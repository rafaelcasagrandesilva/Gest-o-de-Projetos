"""RBAC: add workspace access permissions.

Revision ID: 0047_workspace_permissions
Revises: 0046_receivable_anticipation_received_date
Create Date: 2026-05-13

"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
from sqlalchemy import text


revision = "0047_workspace_permissions"
down_revision = "0046_receivable_anticipation_received_date"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(timezone.utc)

    for code in ("workspace.projects.access", "workspace.finance.access"):
        conn.execute(
            text(
                """
                INSERT INTO permissions (id, created_at, updated_at, name)
                VALUES (gen_random_uuid(), :created_at, :updated_at, :name)
                ON CONFLICT (name) DO NOTHING
                """
            ),
            {"created_at": now, "updated_at": now, "name": code},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        text(
            """
            DELETE FROM permissions
            WHERE name IN ('workspace.projects.access', 'workspace.finance.access')
            """
        )
    )
