"""Modelo de verbos — módulos FINANCEIROS e de LEITURA. Exclusivamente ADITIVA.

Cadastra os códigos de verbo de payables/receivables/invoices/debts/costs/company_finance/billing
(CRUD) e indicators/dashboard/alerts/reports/settings (leitura), e os adiciona aos perfis de sistema.

Mesmas garantias das anteriores: não remove nada; não altera user_permissions. Funcionalmente, os
usuários já operam via grafo (os legados *.view/*.edit implicam os verbos); esta migração é para os
códigos existirem no banco e aparecerem marcados nos perfis na tela de administração.

Revision ID: 0095_verb_permissions_finance
Revises: 0094_verb_permissions_projects
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0095_verb_permissions_finance"
down_revision = "0094_verb_permissions_projects"
branch_labels = None
depends_on = None

_CRUD = ["payables", "receivables", "invoices", "debts", "costs", "company_finance", "billing"]
_CRUD_VERBS = ("list", "read", "create", "update", "delete", "sensitive")
_CRUD_READONLY = ("list", "read", "sensitive")  # CONSULTA

_READ_SENS = ["indicators", "dashboard"]  # read + sensitive
_READ_ONLY = ["alerts", "reports"]  # read

_NEW_CODES: list[str] = []
for r in _CRUD:
    _NEW_CODES += [f"{r}.{v}" for v in _CRUD_VERBS]
for r in _READ_SENS:
    _NEW_CODES += [f"{r}.read", f"{r}.sensitive"]
for r in _READ_ONLY:
    _NEW_CODES += [f"{r}.read"]
_NEW_CODES += ["settings.read", "settings.update"]


def _role_codes(role: str) -> list[str]:
    out: list[str] = []
    if role in ("ADMIN", "GESTOR"):
        out += _NEW_CODES  # acesso pleno
    else:  # CONSULTA — leitura + sensitive, sem escrita
        for r in _CRUD:
            out += [f"{r}.{v}" for v in _CRUD_READONLY]
        for r in _READ_SENS:
            out += [f"{r}.read", f"{r}.sensitive"]
        for r in _READ_ONLY:
            out += [f"{r}.read"]
        out += ["settings.read"]
    return out


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
    for role_name in ("ADMIN", "GESTOR", "CONSULTA"):
        for pname in _role_codes(role_name):
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
        {"names": _NEW_CODES},
    )
    conn.execute(
        sa.text(
            "DELETE FROM permissions p WHERE p.name = ANY(:names) "
            "   AND NOT EXISTS (SELECT 1 FROM user_permissions up WHERE up.permission_id = p.id)"
        ),
        {"names": _NEW_CODES},
    )
