"""permissions: payable_snapshot.reconcile (Reconciliar Snapshot CAP).

Insere no catálogo `permissions` a permissão dedicada da funcionalidade
"Reconciliar Snapshot" de Contas a Pagar. Não vincula a usuários: perfis
(ADMIN/GESTOR) recebem via presets em código (permission_codes.py); concessões
explícitas em user_permissions permanecem inalteradas.

Revision ID: 0069_payable_snapshot_reconcile_permission
Revises: 0068_payable_snapshot_obsolete
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
from sqlalchemy import text

revision = "0069_payable_snapshot_reconcile_permission"
down_revision = "0068_payable_snapshot_obsolete"
branch_labels = None
depends_on = None

_PERMISSION = "payable_snapshot.reconcile"


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
        {"c": now, "u": now, "n": _PERMISSION},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DELETE FROM permissions WHERE name = :n"), {"n": _PERMISSION})
