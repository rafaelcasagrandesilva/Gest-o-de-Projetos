"""RBAC: roles ADMIN, GESTOR, CONSULTA (migração a partir de Admin/Diretor/Gestor/etc.)

Revision ID: 0014_rbac_three_roles
Revises: 0013_receivable_invoices
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision = "0014_rbac_three_roles"
down_revision = "0013_receivable_invoices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(timezone.utc)

    def ensure_role(name: str, description: str) -> str:
        row = conn.execute(text("SELECT id::text FROM roles WHERE name = :n"), {"n": name}).fetchone()
        if row:
            return row[0]
        conn.execute(
            text(
                """
                INSERT INTO roles (id, created_at, updated_at, name, description)
                VALUES (gen_random_uuid(), :c, :u, :name, :d)
                """
            ),
            {"c": now, "u": now, "name": name, "d": description},
        )
        r = conn.execute(text("SELECT id::text FROM roles WHERE name = :n"), {"n": name}).fetchone()
        assert r
        return r[0]

    admin_id = ensure_role("ADMIN", "Acesso total ao sistema")
    gestor_id = ensure_role("GESTOR", "Acesso aos projetos vinculados (project_users)")
    consulta_id = ensure_role("CONSULTA", "Visualização sem alteração de dados")

    # Snapshot: user_id -> set of role names (antes de apagar user_roles)
    user_rows = conn.execute(text("SELECT id::text FROM users")).fetchall()
    user_to_names: dict[str, set[str]] = {}
    for (uid,) in user_rows:
        rows = conn.execute(
            text(
                """
                SELECT r.name FROM user_roles ur
                JOIN roles r ON r.id = ur.role_id
                WHERE ur.user_id = CAST(:uid AS uuid)
                """
            ),
            {"uid": uid},
        ).fetchall()
        user_to_names[uid] = {r[0] for r in rows}

    conn.execute(text("DELETE FROM user_roles"))

    def pick_new_role(names: set[str]) -> str:
        if not names:
            return "CONSULTA"
        if names & {"ADMIN", "Admin", "Diretor"}:
            return "ADMIN"
        if "GESTOR" in names or "Gestor" in names:
            return "GESTOR"
        return "CONSULTA"

    role_id_map = {"ADMIN": admin_id, "GESTOR": gestor_id, "CONSULTA": consulta_id}
    for uid, names in user_to_names.items():
        new_name = pick_new_role(names)
        rid = role_id_map[new_name]
        conn.execute(
            text(
                """
                INSERT INTO user_roles (id, created_at, updated_at, user_id, role_id)
                VALUES (gen_random_uuid(), :c, :u, CAST(:uid AS uuid), CAST(:rid AS uuid))
                """
            ),
            {"c": now, "u": now, "uid": uid, "rid": rid},
        )

    conn.execute(
        text("DELETE FROM roles WHERE name NOT IN ('ADMIN', 'GESTOR', 'CONSULTA')")
    )


def downgrade() -> None:
    # Não restaura nomes antigos; apenas garante que existam os três roles
    pass
