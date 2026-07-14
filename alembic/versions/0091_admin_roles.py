"""Perfis de Usuário administráveis: role_permissions + is_system/is_active em roles +
granted em user_permissions (vínculo vivo perfil→usuário), preservando o efetivo atual.

Contexto: até aqui as permissões de cada perfil eram hardcoded em ROLE_PRESET; os usuários tinham
o conjunto materializado (ou herdavam o preset). Esta migration torna os perfis a FONTE das
permissões (tabela role_permissions) e converte as permissões individuais em DELTAS sobre o perfil:
granted=true = adição individual, granted=false = remoção individual (exceção negativa).

Estratégia de compatibilidade (sem perda de acesso):
- Semeia ADMIN/GESTOR/CONSULTA (is_system=true) com role_permissions = PRESET_ADMIN/GESTOR/CONSULTA.
- Para cada usuário: E = efetivo atual (linhas materializadas; senão união dos presets dos perfis,
  ou CONSULTA se não tiver perfil). RP = união das role_permissions dos perfis do usuário. Reescreve
  user_permissions com adições (E−RP, granted=true) e remoções (RP−E, granted=false). Efetivo pós =
  RP ∪ (E−RP) − (RP−E) = E (idêntico).

Propriedades: aditiva no schema; idempotente no seed (ON CONFLICT). Downgrade dropa as estruturas
novas (os deltas são re-materializáveis; conservador).

Revision ID: 0091_admin_roles
Revises: 0090_decouple_module_permissions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.core.permission_codes import (
    ALL_PERMISSION_CODES,
    PRESET_ADMIN,
    PRESET_CONSULTA,
    PRESET_GESTOR,
)

revision = "0091_admin_roles"
down_revision = "0090_decouple_module_permissions"
branch_labels = None
depends_on = None

_SYSTEM_ROLE_PRESETS: dict[str, frozenset[str]] = {
    "ADMIN": PRESET_ADMIN,
    "GESTOR": PRESET_GESTOR,
    "CONSULTA": PRESET_CONSULTA,
}


def upgrade() -> None:
    # --- Schema (aditivo) ---
    op.add_column("roles", sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("roles", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.create_table(
        "role_permissions",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("role_id", PG_UUID(as_uuid=True), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("permission_id", PG_UUID(as_uuid=True), sa.ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
    )
    op.add_column(
        "user_permissions",
        sa.Column("granted", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    conn = op.get_bind()

    # --- 1) Garante todos os códigos de permissão ---
    for name in ALL_PERMISSION_CODES:
        conn.execute(
            sa.text(
                "INSERT INTO permissions (id, created_at, updated_at, name) "
                "VALUES (gen_random_uuid(), now(), now(), :n) ON CONFLICT (name) DO NOTHING"
            ),
            {"n": name},
        )

    # --- 2) Perfis de sistema + is_system + seed role_permissions ---
    for role_name, preset in _SYSTEM_ROLE_PRESETS.items():
        conn.execute(
            sa.text(
                "INSERT INTO roles (id, created_at, updated_at, name, description, is_system, is_active) "
                "VALUES (gen_random_uuid(), now(), now(), :n, :d, true, true) "
                "ON CONFLICT (name) DO UPDATE SET is_system = true"
            ),
            {"n": role_name, "d": f"Perfil de sistema {role_name}"},
        )
        for pname in sorted(preset):
            conn.execute(
                sa.text(
                    "INSERT INTO role_permissions (id, created_at, updated_at, role_id, permission_id) "
                    "SELECT gen_random_uuid(), now(), now(), r.id, p.id "
                    "  FROM roles r, permissions p WHERE r.name = :r AND p.name = :p "
                    "ON CONFLICT (role_id, permission_id) DO NOTHING"
                ),
                {"r": role_name, "p": pname},
            )

    # --- 3) Converte user_permissions (lista materializada) em DELTAS sobre o(s) perfil(is) ---
    # Efetivo preservado por construção: novo = (roleperms ∪ adds) − removes, onde
    #   adds    = permissões que o usuário tinha e o perfil NÃO concede  (granted=true)
    #   removes = permissões que o perfil concede e o usuário NÃO tinha  (granted=false)
    # e as permissões em (tinha ∩ perfil) deixam de ter linha (passam a seguir o perfil).
    # Só usuários MATERIALIZADOS (com linhas hoje) geram removes — usuários que herdavam o preset
    # (sem linhas) continuam sem deltas, seguindo integralmente o perfil.
    conn.execute(sa.text("CREATE TEMP TABLE _orig_up AS SELECT DISTINCT user_id, permission_id FROM user_permissions"))
    conn.execute(sa.text("DELETE FROM user_permissions"))

    # adds: originais que nenhum perfil do usuário concede
    conn.execute(
        sa.text(
            "INSERT INTO user_permissions (id, created_at, updated_at, user_id, permission_id, granted) "
            "SELECT gen_random_uuid(), now(), now(), o.user_id, o.permission_id, true "
            "  FROM _orig_up o "
            " WHERE NOT EXISTS ( "
            "         SELECT 1 FROM role_permissions rp JOIN user_roles ur ON ur.role_id = rp.role_id "
            "          WHERE ur.user_id = o.user_id AND rp.permission_id = o.permission_id) "
        )
    )
    # removes: permissões do perfil que o usuário (materializado) NÃO tinha
    conn.execute(
        sa.text(
            "INSERT INTO user_permissions (id, created_at, updated_at, user_id, permission_id, granted) "
            "SELECT gen_random_uuid(), now(), now(), ur.user_id, rp.permission_id, false "
            "  FROM role_permissions rp JOIN user_roles ur ON ur.role_id = rp.role_id "
            " WHERE ur.user_id IN (SELECT DISTINCT user_id FROM _orig_up) "
            "   AND NOT EXISTS (SELECT 1 FROM _orig_up o "
            "                    WHERE o.user_id = ur.user_id AND o.permission_id = rp.permission_id) "
            " GROUP BY ur.user_id, rp.permission_id"
        )
    )
    conn.execute(sa.text("DROP TABLE _orig_up"))


def downgrade() -> None:
    # Remove as estruturas novas. Os deltas (granted=false) são descartados; as adições permanecem
    # como user_permissions materializadas — o código legado volta a tratá-las como lista efetiva.
    op.execute("DELETE FROM user_permissions WHERE granted = false")
    op.drop_column("user_permissions", "granted")
    op.drop_table("role_permissions")
    op.drop_column("roles", "is_active")
    op.drop_column("roles", "is_system")
