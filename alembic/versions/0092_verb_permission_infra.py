"""Etapa 0 do modelo de permissões por verbos — INFRAESTRUTURA, exclusivamente ADITIVA.

Objetivo único: cadastrar os NOVOS códigos de permissão (modelo de verbos) na tabela `permissions`
e adicioná-los aos perfis de SISTEMA (ADMIN/GESTOR/CONSULTA), equivalentes ao que cada perfil já
concede hoje pelos códigos legados `<recurso>.view`/`<recurso>.edit`.

GARANTIAS (deploy funcionalmente neutro):
- NÃO remove nenhuma permissão nem vínculo existente.
- NÃO altera `user_permissions` (nenhum delta é recalculado; nenhum usuário é modificado).
- NÃO altera schema (nenhuma coluna/tabela nova).
- Os códigos novos nascem INATIVOS no código (`ACTIVE_PERMISSION_CODES`): não entram na sessão do
  usuário e nenhum endpoint os checa nesta etapa. Semear os perfis agora só evita mistura de códigos
  antigos/novos quando cada módulo for ativado nas etapas seguintes.

Idempotente (ON CONFLICT DO NOTHING). Downgrade remove apenas o que esta migration adicionou.

Revision ID: 0092_verb_permission_infra
Revises: 0091_admin_roles
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0092_verb_permission_infra"
down_revision = "0091_admin_roles"
branch_labels = None
depends_on = None

# Códigos NOVOS introduzidos nesta etapa (congelados aqui para a migration ser autocontida).
_NEW_CODES: tuple[str, ...] = (
    "employees.reference",
    "employees.list",
    "employees.read",
    "employees.create",
    "employees.update",
    "employees.delete",
    "employees.sensitive",
    "assets.reference",
    "assets.list",
    "assets.read",
    "assets.create",
    "assets.update",
    "assets.delete",
    "assets.sensitive",
    "cost_center.reference",
)

# Códigos novos por perfil de sistema (equivalentes ao efetivo atual de cada perfil).
_EMPLOYEES_FULL = (
    "employees.reference",
    "employees.list",
    "employees.read",
    "employees.create",
    "employees.update",
    "employees.delete",
    "employees.sensitive",
)
_ASSETS_FULL = (
    "assets.reference",
    "assets.list",
    "assets.read",
    "assets.create",
    "assets.update",
    "assets.delete",
    "assets.sensitive",
)
_EMPLOYEES_READ_ONLY = (
    "employees.reference",
    "employees.list",
    "employees.read",
    "employees.sensitive",
)
_ASSETS_READ_ONLY = (
    "assets.reference",
    "assets.list",
    "assets.read",
)

_ROLE_NEW_CODES: dict[str, tuple[str, ...]] = {
    # ADMIN tem acesso irrestrito; recebe tudo por completude do catálogo.
    "ADMIN": _NEW_CODES,
    # GESTOR tem *.edit legado → CRUD completo + sensitive.
    "GESTOR": _EMPLOYEES_FULL + _ASSETS_FULL + ("cost_center.reference",),
    # CONSULTA tem *.view legado → leitura + sensitive, sem CRUD.
    "CONSULTA": _EMPLOYEES_READ_ONLY + _ASSETS_READ_ONLY + ("cost_center.reference",),
}


def upgrade() -> None:
    conn = op.get_bind()

    # 1) Garante os códigos novos em `permissions` (idempotente).
    for name in _NEW_CODES:
        conn.execute(
            sa.text(
                "INSERT INTO permissions (id, created_at, updated_at, name) "
                "VALUES (gen_random_uuid(), now(), now(), :n) ON CONFLICT (name) DO NOTHING"
            ),
            {"n": name},
        )

    # 2) Adiciona os códigos novos aos perfis de sistema (aditivo; nunca remove).
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

    # 3) user_permissions: intocada (por design).


def downgrade() -> None:
    conn = op.get_bind()

    # Remove os vínculos de role criados por esta migration (qualquer role, defensivo).
    conn.execute(
        sa.text(
            "DELETE FROM role_permissions rp "
            " USING permissions p "
            " WHERE rp.permission_id = p.id AND p.name = ANY(:names)"
        ),
        {"names": list(_NEW_CODES)},
    )

    # Remove as linhas de `permissions` dos códigos novos SOMENTE se ninguém as referenciar em
    # user_permissions (por design, esta etapa nunca grava lá — a guarda é defensiva).
    conn.execute(
        sa.text(
            "DELETE FROM permissions p "
            " WHERE p.name = ANY(:names) "
            "   AND NOT EXISTS (SELECT 1 FROM user_permissions up WHERE up.permission_id = p.id)"
        ),
        {"names": list(_NEW_CODES)},
    )
