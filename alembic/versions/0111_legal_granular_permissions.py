"""Jurídico — permissões GRANULARES por menu. Escopo restrito ao módulo Jurídico.

Substitui o recurso único `legal.*` (7 códigos, criado na 0109) por um recurso PRÓPRIO por MENU,
seguindo o isolamento por módulo do resto do sistema:

    legal_dashboard.read
    legal_cases.{reference,list,read,create,update,delete,export,sensitive}
    legal_persons.{reference,list,read,create,update,delete,export,sensitive}
    legal_companies.{list,read,create,update,delete}
    legal_projects.{list,read,create,update,delete}
    legal_reports.{read,export}

`workspace.legal.access` permanece inalterado.

**Conversão sem perda e sem ganho de acesso:** cada perfil/usuário que tinha um código `legal.*`
recebe exatamente os códigos novos equivalentes (o mapa `_EQUIVALENCE` reproduz o que aquele código
concedia). Só depois os `legal.*` são removidos. Quem tinha `legal.sensitive` recebe o `sensitive`
de Processos E de Desligados — era o que aquele código único cobria.

**Nada fora do Jurídico é tocado:** todas as consultas filtram por `p.name LIKE 'legal.%'` ou pela
lista explícita de códigos novos. Nenhuma permissão de outro módulo é criada, alterada ou removida,
e `user_permissions` de outros recursos permanece intacto.

Revision ID: 0111_legal_granular_permissions
Revises: 0110_legal_admin_catalogs
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0111_legal_granular_permissions"
down_revision = "0110_legal_admin_catalogs"
branch_labels = None
depends_on = None

# Código ANTIGO → códigos NOVOS que reproduzem exatamente o que ele concedia.
_EQUIVALENCE: dict[str, tuple[str, ...]] = {
    "legal.reference": ("legal_cases.reference", "legal_persons.reference"),
    "legal.list": (
        "legal_dashboard.read",
        "legal_cases.list",
        "legal_persons.list",
        "legal_companies.list",
        "legal_projects.list",
        "legal_reports.read",
    ),
    "legal.read": ("legal_cases.read", "legal_persons.read", "legal_companies.read", "legal_projects.read"),
    "legal.create": ("legal_cases.create", "legal_persons.create", "legal_companies.create", "legal_projects.create"),
    "legal.update": ("legal_cases.update", "legal_persons.update", "legal_companies.update", "legal_projects.update"),
    "legal.delete": ("legal_cases.delete", "legal_persons.delete", "legal_companies.delete", "legal_projects.delete"),
    "legal.sensitive": ("legal_cases.sensitive", "legal_persons.sensitive"),
}

# Exportar não existia no modelo antigo: quem podia LISTAR passa a poder exportar o que já via
# (mesma regra de employees.export/vehicles.export, que acompanham a leitura do módulo).
_EXPORT_FOR_LIST: tuple[str, ...] = (
    "legal_cases.export",
    "legal_persons.export",
    "legal_reports.export",
)

_OLD_CODES: tuple[str, ...] = tuple(_EQUIVALENCE)
_NEW_CODES: tuple[str, ...] = tuple(
    dict.fromkeys([c for codes in _EQUIVALENCE.values() for c in codes] + list(_EXPORT_FOR_LIST))
)


def _register(conn, codes: tuple[str, ...]) -> None:
    for name in codes:
        conn.execute(
            sa.text(
                "INSERT INTO permissions (id, created_at, updated_at, name) "
                "VALUES (gen_random_uuid(), now(), now(), :n) ON CONFLICT (name) DO NOTHING"
            ),
            {"n": name},
        )


def _copy_grants(conn, old: str, new_codes: tuple[str, ...]) -> None:
    """Replica, para cada código novo, os vínculos (perfil e usuário) que o código antigo tinha."""
    for new in new_codes:
        conn.execute(
            sa.text(
                "INSERT INTO role_permissions (id, created_at, updated_at, role_id, permission_id) "
                "SELECT gen_random_uuid(), now(), now(), rp.role_id, np.id "
                "  FROM role_permissions rp "
                "  JOIN permissions op ON op.id = rp.permission_id AND op.name = :old "
                "  JOIN permissions np ON np.name = :new "
                "ON CONFLICT (role_id, permission_id) DO NOTHING"
            ),
            {"old": old, "new": new},
        )
        # `granted` é preservado: uma REMOÇÃO individual (granted=false) continua sendo remoção.
        conn.execute(
            sa.text(
                "INSERT INTO user_permissions (id, created_at, updated_at, user_id, permission_id, granted) "
                "SELECT gen_random_uuid(), now(), now(), up.user_id, np.id, up.granted "
                "  FROM user_permissions up "
                "  JOIN permissions op ON op.id = up.permission_id AND op.name = :old "
                "  JOIN permissions np ON np.name = :new "
                "ON CONFLICT (user_id, permission_id) DO NOTHING"
            ),
            {"old": old, "new": new},
        )


def upgrade() -> None:
    conn = op.get_bind()

    _register(conn, _NEW_CODES)
    for old, new_codes in _EQUIVALENCE.items():
        _copy_grants(conn, old, new_codes)
    # Exportação acompanha quem listava.
    _copy_grants(conn, "legal.list", _EXPORT_FOR_LIST)

    # Remove os códigos antigos (e só eles).
    conn.execute(
        sa.text(
            "DELETE FROM role_permissions rp USING permissions p "
            " WHERE rp.permission_id = p.id AND p.name = ANY(:old)"
        ),
        {"old": list(_OLD_CODES)},
    )
    conn.execute(
        sa.text(
            "DELETE FROM user_permissions up USING permissions p "
            " WHERE up.permission_id = p.id AND p.name = ANY(:old)"
        ),
        {"old": list(_OLD_CODES)},
    )
    conn.execute(sa.text("DELETE FROM permissions WHERE name = ANY(:old)"), {"old": list(_OLD_CODES)})


def downgrade() -> None:
    """Recria os `legal.*` a partir dos granulares e remove os novos (volta ao estado da 0109)."""
    conn = op.get_bind()

    _register(conn, _OLD_CODES)
    # O antigo volta a existir para quem tem TODOS os equivalentes do código (conversão inversa fiel).
    for old, new_codes in _EQUIVALENCE.items():
        conn.execute(
            sa.text(
                "INSERT INTO role_permissions (id, created_at, updated_at, role_id, permission_id) "
                "SELECT gen_random_uuid(), now(), now(), rp.role_id, op.id "
                "  FROM role_permissions rp "
                "  JOIN permissions np ON np.id = rp.permission_id AND np.name = ANY(:new) "
                "  JOIN permissions op ON op.name = :old "
                " GROUP BY rp.role_id, op.id "
                "HAVING count(DISTINCT np.name) = :total "
                "ON CONFLICT (role_id, permission_id) DO NOTHING"
            ),
            {"new": list(new_codes), "old": old, "total": len(new_codes)},
        )

    for table, col in (("role_permissions", "role_id"), ("user_permissions", "user_id")):
        conn.execute(
            sa.text(
                f"DELETE FROM {table} t USING permissions p "
                " WHERE t.permission_id = p.id AND p.name = ANY(:new)"
            ),
            {"new": list(_NEW_CODES)},
        )
    conn.execute(sa.text("DELETE FROM permissions WHERE name = ANY(:new)"), {"new": list(_NEW_CODES)})
