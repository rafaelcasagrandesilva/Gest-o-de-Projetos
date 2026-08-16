"""Remove `legal_cases.export` e `legal_persons.export` — permissões sem endpoint.

Limpeza da Release Candidate. As duas foram criadas pela 0111 (`_EXPORT_FOR_LIST`) por simetria
com `employees.export`/`vehicles.export`, mas nunca chegaram a governar nada: as telas de
Processos e Desligados não têm exportação própria, e o arquivo do módulo sai pelo relatório,
gateado por `legal_reports.export` (que PERMANECE).

**Nenhuma capacidade é perdida.** Pelo grafo de implicação, cada uma concedia apenas
`legal_cases.list` / `legal_persons.list` — que todo perfil que as possuía já tem por outro
caminho (a 0111 as copiou justamente de quem tinha `legal.list`). Confirmado antes de escrever
esta migration: 0 perfis e 0 usuários ficam sem `list` ao removê-las.

Voltam a existir quando houver um botão de exportar por tela.

Revision ID: 0118_drop_legal_case_person_export
Revises: 0117_legal_import_runs
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0118_drop_legal_case_person_export"
down_revision = "0117_legal_import_runs"
branch_labels = None
depends_on = None

_CODES: tuple[str, ...] = ("legal_cases.export", "legal_persons.export")

# Código removido → o que ele implicava. Usado no downgrade para restaurar os vínculos
# exatamente para quem tem a permissão implicada (conversão inversa fiel).
_IMPLIED: dict[str, str] = {
    "legal_cases.export": "legal_cases.list",
    "legal_persons.export": "legal_persons.list",
}


def upgrade() -> None:
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


def downgrade() -> None:
    """Recria os códigos e devolve a quem tem a permissão de LISTAR do mesmo recurso."""
    conn = op.get_bind()
    for code, implied in _IMPLIED.items():
        conn.execute(
            sa.text(
                "INSERT INTO permissions (id, created_at, updated_at, name) "
                "VALUES (gen_random_uuid(), now(), now(), :n) ON CONFLICT (name) DO NOTHING"
            ),
            {"n": code},
        )
        conn.execute(
            sa.text(
                "INSERT INTO role_permissions (id, created_at, updated_at, role_id, permission_id) "
                "SELECT gen_random_uuid(), now(), now(), rp.role_id, np.id "
                "  FROM role_permissions rp "
                "  JOIN permissions op ON op.id = rp.permission_id AND op.name = :implied "
                "  JOIN permissions np ON np.name = :code "
                "ON CONFLICT (role_id, permission_id) DO NOTHING"
            ),
            {"implied": implied, "code": code},
        )
