"""Modelo de permissões por verbos — VEÍCULOS. Exclusivamente ADITIVA.

Cadastra os códigos vehicles.{reference,list,read,create,update,delete,sensitive} em `permissions`
e os adiciona aos perfis de SISTEMA (ADMIN/GESTOR/CONSULTA), equivalentes ao que cada perfil já
concede hoje por vehicles.view/vehicles.edit.

Mesmas garantias da 0092: NÃO remove nada; NÃO altera `user_permissions`; NÃO recalcula deltas.
Idempotente (ON CONFLICT DO NOTHING). Downgrade remove apenas o que esta migration adicionou.

Revision ID: 0093_verb_permissions_vehicles
Revises: 0092_verb_permission_infra
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0093_verb_permissions_vehicles"
down_revision = "0092_verb_permission_infra"
branch_labels = None
depends_on = None

_NEW_CODES: tuple[str, ...] = (
    "vehicles.reference",
    "vehicles.list",
    "vehicles.read",
    "vehicles.create",
    "vehicles.update",
    "vehicles.delete",
    "vehicles.sensitive",
)

_VEHICLES_FULL = _NEW_CODES  # CRUD completo + sensitive (equivale a vehicles.edit legado)
_VEHICLES_READ_ONLY = (
    "vehicles.reference",
    "vehicles.list",
    "vehicles.read",
    "vehicles.sensitive",
)  # equivale a vehicles.view legado

_ROLE_NEW_CODES: dict[str, tuple[str, ...]] = {
    "ADMIN": _NEW_CODES,
    "GESTOR": _VEHICLES_FULL,
    "CONSULTA": _VEHICLES_READ_ONLY,
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
    # user_permissions: intocada (por design).


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
            "DELETE FROM permissions p "
            " WHERE p.name = ANY(:names) "
            "   AND NOT EXISTS (SELECT 1 FROM user_permissions up WHERE up.permission_id = p.id)"
        ),
        {"names": list(_NEW_CODES)},
    )
