"""permissions + user_permissions; seed a partir dos roles atuais.

- PK `permissions.id` e `user_permissions.id`: UUID (alinha ao TimestampUUIDMixin / ORM).
- Seed: todas as permissões de negócio + vínculos por usuário conforme role (ADMIN = todas).

Revision ID: 0020_permissions_rbac
Revises: 0019_pv_fuel_real
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0020_permissions_rbac"
down_revision = "0019_pv_fuel_real"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(timezone.utc)

    op.create_table(
        "permissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_permissions_name"), "permissions", ["name"], unique=False)

    op.create_table(
        "user_permissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("permission_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "permission_id", name="uq_user_permission"),
    )

    codes = (
        "system.admin",
        "system.all_projects",
        "dashboard.view",
        "dashboard.director",
        "projects.view",
        "projects.create",
        "projects.edit",
        "projects.delete",
        "employees.view",
        "employees.edit",
        "vehicles.view",
        "vehicles.edit",
        "billing.view",
        "invoices.view",
        "invoices.edit",
        "debts.view",
        "debts.edit",
        "costs.view",
        "costs.edit",
        "settings.view",
        "settings.edit",
        "users.manage",
        "reports.view",
        "reports.export",
        "alerts.view",
        "company_finance.view",
        "company_finance.edit",
    )

    name_to_id: dict[str, str] = {}
    for c in codes:
        conn.execute(
            text(
                """
                INSERT INTO permissions (id, created_at, updated_at, name)
                VALUES (gen_random_uuid(), :c, :u, :n)
                """
            ),
            {"c": now, "u": now, "n": c},
        )
        r = conn.execute(text("SELECT id::text FROM permissions WHERE name = :n"), {"n": c}).fetchone()
        assert r
        name_to_id[c] = r[0]

    rows = conn.execute(
        text(
            """
            SELECT DISTINCT ON (u.id) u.id::text, COALESCE(r.name, 'CONSULTA') AS role_name
            FROM users u
            LEFT JOIN user_roles ur ON ur.user_id = u.id
            LEFT JOIN roles r ON r.id = ur.role_id
            ORDER BY u.id, r.name NULLS LAST
            """
        )
    ).fetchall()

    def preset_for_role(role_name: str) -> set[str]:
        if role_name == "ADMIN":
            return set(codes)
        if role_name == "GESTOR":
            return set(codes) - {"users.manage", "system.admin", "system.all_projects"}
        return {
            "dashboard.view",
            "projects.view",
            "employees.view",
            "vehicles.view",
            "billing.view",
            "invoices.view",
            "debts.view",
            "costs.view",
            "reports.view",
            "alerts.view",
            "company_finance.view",
        }

    done: set[str] = set()
    for uid, role_name in rows:
        if uid in done:
            continue
        done.add(uid)
        rn = role_name or "CONSULTA"
        perms = preset_for_role(rn)

        for pname in perms:
            pid = name_to_id.get(pname)
            if not pid:
                continue
            conn.execute(
                text(
                    """
                    INSERT INTO user_permissions (id, created_at, updated_at, user_id, permission_id)
                    VALUES (gen_random_uuid(), :c, :u, CAST(:uid AS uuid), CAST(:pid AS uuid))
                    """
                ),
                {"c": now, "u": now, "uid": uid, "pid": pid},
            )


def downgrade() -> None:
    op.drop_table("user_permissions")
    op.drop_table("permissions")
