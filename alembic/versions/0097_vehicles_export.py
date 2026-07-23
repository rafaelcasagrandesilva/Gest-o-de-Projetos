"""Modelo de verbos — VEÍCULOS: permissão `vehicles.export`. Exclusivamente ADITIVA.

Mesmo padrão de 0096 (employees.export): cadastra `vehicles.export` em `permissions` e o adiciona aos
perfis de SISTEMA ADMIN e GESTOR. CONSULTA (somente leitura) não recebe. Exportações de recurso
específico usam `<recurso>.export` próprio; `reports.export` fica restrito ao módulo Relatórios.

Garantias: NÃO remove nada; NÃO altera `user_permissions`; NÃO recalcula deltas. Idempotente
(ON CONFLICT DO NOTHING). Downgrade remove apenas o que esta migration adicionou.

Revision ID: 0097_vehicles_export
Revises: 0096_employees_export
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0097_vehicles_export"
down_revision = "0096_employees_export"
branch_labels = None
depends_on = None

_NEW_CODES: tuple[str, ...] = ("vehicles.export",)

_ROLE_NEW_CODES: dict[str, tuple[str, ...]] = {
    "ADMIN": _NEW_CODES,
    "GESTOR": _NEW_CODES,
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
