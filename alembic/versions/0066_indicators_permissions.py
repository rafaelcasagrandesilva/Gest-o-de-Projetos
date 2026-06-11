"""permissions: workspace Indicadores (ROI Operacional).

Insere no catálogo `permissions` as 3 permissões do novo workspace de
indicadores. Não vincula a usuários/perfis: perfis (ADMIN/GESTOR/CONSULTA)
recebem via presets em código (permission_codes.py); usuários com permissões
explícitas em user_permissions continuam inalterados (concessão manual posterior).

Revision ID: 0066_indicators_permissions
Revises: 0065_audit_export_permission
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
from sqlalchemy import text

revision = "0066_indicators_permissions"
down_revision = "0065_audit_export_permission"
branch_labels = None
depends_on = None

_PERMISSIONS = (
    "workspace.indicators.access",
    "indicators.view",
    "indicators.director",
)


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(timezone.utc)
    for name in _PERMISSIONS:
        conn.execute(
            text(
                """
                INSERT INTO permissions (id, created_at, updated_at, name)
                VALUES (gen_random_uuid(), :c, :u, :n)
                ON CONFLICT (name) DO NOTHING
                """
            ),
            {"c": now, "u": now, "n": name},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        text("DELETE FROM permissions WHERE name IN ('workspace.indicators.access', 'indicators.view', 'indicators.director')")
    )
