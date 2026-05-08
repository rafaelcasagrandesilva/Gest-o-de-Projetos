"""Fix: increase alembic_version.version_num size to avoid overflow.

Some environments were created with `alembic_version.version_num` as VARCHAR(32),
but our revision ids can be longer than 32 characters (e.g. descriptive ids).

Revision ID: 0026_fix_alembic_version_column
Revises: 0025_add_payables_receivables_permissions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0026_fix_alembic_version_column"
down_revision = "0024_receivable_simplified"
branch_labels = None
depends_on = None


def _current_varchar_len() -> int | None:
    conn = op.get_bind()
    # Postgres: information_schema returns character_maximum_length for varchar columns.
    row = conn.execute(
        text(
            """
            SELECT character_maximum_length
            FROM information_schema.columns
            WHERE table_name = 'alembic_version'
              AND column_name = 'version_num'
            """
        )
    ).fetchone()
    if not row:
        return None
    return int(row[0]) if row[0] is not None else None


def upgrade() -> None:
    cur = _current_varchar_len()
    # Idempotente: se já for >= 100 (ou sem limite), não altera.
    if cur is None or cur >= 100:
        return
    op.alter_column("alembic_version", "version_num", type_=sa.String(length=100))


def downgrade() -> None:
    cur = _current_varchar_len()
    # Idempotente: só reduz se estiver maior que 32.
    if cur is None or cur <= 32:
        return
    op.alter_column("alembic_version", "version_num", type_=sa.String(length=32))

