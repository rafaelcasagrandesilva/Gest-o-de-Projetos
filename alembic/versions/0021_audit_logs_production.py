"""audit_logs: field_changes, context, IP/UA, user_email; rename actor_user_id -> user_id.

Revision ID: 0021_audit_logs_production
Revises: 0020_permissions_rbac
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021_audit_logs_production"
down_revision = "0020_permissions_rbac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_logs", sa.Column("user_email", sa.String(length=255), nullable=True))
    op.add_column(
        "audit_logs",
        sa.Column("field_changes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "audit_logs",
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("audit_logs", sa.Column("ip_address", sa.String(length=64), nullable=True))
    op.add_column("audit_logs", sa.Column("user_agent", sa.String(length=512), nullable=True))

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE audit_logs
            SET context = jsonb_build_object(
                'legacy',
                jsonb_build_object('before', before, 'after', after)
            )
            WHERE before IS NOT NULL OR after IS NOT NULL
            """
        )
    )

    op.drop_index("ix_audit_logs_occurred_at", table_name="audit_logs")
    op.drop_column("audit_logs", "occurred_at")
    op.drop_column("audit_logs", "before")
    op.drop_column("audit_logs", "after")

    op.execute(sa.text("ALTER TABLE audit_logs RENAME COLUMN actor_user_id TO user_id"))

    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"], unique=False)
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")

    op.execute(sa.text("ALTER TABLE audit_logs RENAME COLUMN user_id TO actor_user_id"))

    op.add_column(
        "audit_logs",
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "audit_logs",
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "audit_logs",
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE audit_logs
            SET
                before = context->'legacy'->'before',
                after = context->'legacy'->'after'
            WHERE context ? 'legacy'
            """
        )
    )

    op.drop_column("audit_logs", "user_agent")
    op.drop_column("audit_logs", "ip_address")
    op.drop_column("audit_logs", "field_changes")
    op.drop_column("audit_logs", "user_email")
    op.drop_column("audit_logs", "context")

    op.create_index("ix_audit_logs_occurred_at", "audit_logs", ["occurred_at"], unique=False)
