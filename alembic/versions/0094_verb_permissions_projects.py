"""Modelo de verbos — PROJETOS. Exclusivamente ADITIVA.

Cadastra projects.{reference,list,read,update,sensitive} e os adiciona aos perfis de sistema,
equivalentes ao que cada perfil já concede por projects.view/projects.edit.

Mesmas garantias das 0092/0093: não remove nada; não altera user_permissions.

Revision ID: 0094_verb_permissions_projects
Revises: 0093_verb_permissions_vehicles
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0094_verb_permissions_projects"
down_revision = "0093_verb_permissions_vehicles"
branch_labels = None
depends_on = None

_NEW_CODES = (
    "projects.reference",
    "projects.list",
    "projects.read",
    "projects.update",
    "projects.sensitive",
)

# GESTOR já edita projetos → update + leitura + sensitive. CONSULTA lê (com valores) → leitura + sensitive.
_ROLE_NEW_CODES = {
    "ADMIN": _NEW_CODES,
    "GESTOR": ("projects.reference", "projects.list", "projects.read", "projects.update", "projects.sensitive"),
    "CONSULTA": ("projects.reference", "projects.list", "projects.read", "projects.sensitive"),
}


def upgrade() -> None:
    conn = op.get_bind()
    for name in _NEW_CODES:
        conn.execute(
            sa.text(
                "INSERT INTO permissions (id, created_at, updated_at, name) "
                "VALUES (gen_random_uuid(), now(), now(), :n) ON CONFLICT (name) DO NOTHING"
            ),
            {"n": name},
        )
    for role_name, codes in _ROLE_NEW_CODES.items():
        for pname in codes:
            conn.execute(
                sa.text(
                    "INSERT INTO role_permissions (id, created_at, updated_at, role_id, permission_id) "
                    "SELECT gen_random_uuid(), now(), now(), r.id, p.id "
                    "  FROM roles r, permissions p "
                    " WHERE r.name = :r AND r.is_system = true AND p.name = :p "
                    "ON CONFLICT (role_id, permission_id) DO NOTHING"
                ),
                {"r": role_name, "p": pname},
            )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM role_permissions rp USING permissions p "
            " WHERE rp.permission_id = p.id AND p.name = ANY(:names)"
        ),
        {"names": list(_NEW_CODES)},
    )
    conn.execute(
        sa.text(
            "DELETE FROM permissions p WHERE p.name = ANY(:names) "
            "   AND NOT EXISTS (SELECT 1 FROM user_permissions up WHERE up.permission_id = p.id)"
        ),
        {"names": list(_NEW_CODES)},
    )
