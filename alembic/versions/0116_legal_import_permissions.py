"""Jurídico — permissões do menu Importações. Exclusivamente ADITIVA.

Cria o recurso `legal_imports` (`list` e `create`), que passa a governar a carga da planilha
oficial do módulo. Recurso PRÓPRIO por dois motivos: Importações é um MENU (mesma regra dos
demais recursos do Jurídico) e importar escreve em Processos E em Desligados de uma só vez —
um poder distinto de editar um registro pela tela.

**Quem recebe:** exatamente os perfis que já administram o módulo — os que hoje possuem
`legal_cases.create` E `legal_persons.create` (na prática ADMIN e GESTOR), além de qualquer
perfil com `system.admin`. Um perfil somente-leitura como CONSULTA NÃO recebe nada: ele não tem
`create` em nenhum dos dois recursos. Nenhuma permissão existente é criada, alterada ou removida.

Sem concessões individuais em `user_permissions`: quem precisar importar sem ter o perfil recebe
a permissão pela tela de usuários, como qualquer outra.

Revision ID: 0116_legal_import_permissions
Revises: 0115_assignment_cancelled
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0116_legal_import_permissions"
down_revision = "0115_assignment_cancelled"
branch_labels = None
depends_on = None

_CODES: tuple[str, ...] = ("legal_imports.list", "legal_imports.create")

# Perfil que já pode CRIAR processos e desligados administra o módulo — é quem importa.
_REQUIRED: tuple[str, ...] = ("legal_cases.create", "legal_persons.create")


def upgrade() -> None:
    conn = op.get_bind()

    for name in _CODES:
        conn.execute(
            sa.text(
                "INSERT INTO permissions (id, created_at, updated_at, name) "
                "VALUES (gen_random_uuid(), now(), now(), :n) ON CONFLICT (name) DO NOTHING"
            ),
            {"n": name},
        )

    for name in _CODES:
        conn.execute(
            sa.text(
                "INSERT INTO role_permissions (id, created_at, updated_at, role_id, permission_id) "
                "SELECT gen_random_uuid(), now(), now(), r.role_id, np.id "
                "  FROM ( "
                "        SELECT rp.role_id "
                "          FROM role_permissions rp "
                "          JOIN permissions p ON p.id = rp.permission_id "
                "         WHERE p.name = ANY(:required) "
                "         GROUP BY rp.role_id "
                "        HAVING count(DISTINCT p.name) = :total "
                "        UNION "
                "        SELECT rp.role_id "
                "          FROM role_permissions rp "
                "          JOIN permissions p ON p.id = rp.permission_id "
                "         WHERE p.name = 'system.admin' "
                "       ) r "
                "  JOIN permissions np ON np.name = :new "
                "ON CONFLICT (role_id, permission_id) DO NOTHING"
            ),
            {"required": list(_REQUIRED), "total": len(_REQUIRED), "new": name},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for table in ("role_permissions", "user_permissions"):
        conn.execute(
            sa.text(
                f"DELETE FROM {table} t USING permissions p "
                " WHERE t.permission_id = p.id AND p.name = ANY(:codes)"
            ),
            {"codes": list(_CODES)},
        )
    conn.execute(sa.text("DELETE FROM permissions WHERE name = ANY(:codes)"), {"codes": list(_CODES)})
