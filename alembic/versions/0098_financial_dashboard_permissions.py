"""Dados Sensíveis — DASHBOARD FINANCEIRO: recurso próprio. Exclusivamente ADITIVA.

Cadastra os códigos `financial_dashboard.read` (acesso à tela) e `financial_dashboard.sensitive`
(receber os valores: faturamento/pago/caixa e composições) em `permissions` e os adiciona aos perfis
que HOJE têm acesso ao Dashboard Financeiro — preservando 100% do acesso e da visibilidade atuais.

Contexto: antes desta feature a tela reusava `billing.read` (Faturamento) como gate e NÃO passava
por `redact_for` (sem recurso próprio nem redação). Agora tem recurso PRÓPRIO (espelha o Dashboard de
Projetos). Para NÃO quebrar acesso, semeia `read + sensitive` em TODO perfil (de sistema OU custom)
que hoje concede leitura de Faturamento — isto é, que tenha qualquer código que implique `billing.read`
no grafo: billing.view/edit/read/create/update/delete. Como antes não havia redação, quem tinha acesso
via valores; por isso semeamos também `sensitive` (mantém a visibilidade atual). A partir daqui, um
admin pode REMOVER `financial_dashboard.sensitive` (delta ou no perfil) para ocultar só os valores,
sem perder o acesso — a nova capacidade pedida na homologação.

Diferente das 0095/0096 (que tocaram só perfis de sistema porque os legados já operavam via grafo),
aqui NÃO existe caminho no grafo até `financial_dashboard.read`; então semear os perfis custom que já
tinham acesso é necessário para não regredir. Continua puramente ADITIVA: nada é removido; nenhum
`user_permissions` é tocado; idempotente (ON CONFLICT DO NOTHING).

Revision ID: 0098_financial_dashboard_permissions
Revises: 0097_vehicles_export
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0098_financial_dashboard_permissions"
down_revision = "0097_vehicles_export"
branch_labels = None
depends_on = None

_NEW_CODES: tuple[str, ...] = ("financial_dashboard.read", "financial_dashboard.sensitive")

# Códigos de Faturamento que concedem LEITURA (billing.read direto ou via implicação no grafo).
# billing.list NÃO entra (list < read; ter só list não abria o dashboard).
_BILLING_READ_GRANTING: tuple[str, ...] = (
    "billing.view", "billing.edit", "billing.read",
    "billing.create", "billing.update", "billing.delete",
)


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

    # Semeia read + sensitive em TODO perfil (sistema OU custom) que hoje concede leitura de Faturamento.
    for pname in _NEW_CODES:
        conn.execute(
            sa.text(
                "INSERT INTO role_permissions (id, created_at, updated_at, role_id, permission_id) "
                "SELECT gen_random_uuid(), now(), now(), r.id, np.id "
                "  FROM roles r "
                "  JOIN role_permissions rp ON rp.role_id = r.id "
                "  JOIN permissions bp ON bp.id = rp.permission_id AND bp.name = ANY(:billing) "
                "  JOIN permissions np ON np.name = :new "
                " GROUP BY r.id, np.id "
                "ON CONFLICT (role_id, permission_id) DO NOTHING"
            ),
            {"billing": list(_BILLING_READ_GRANTING), "new": pname},
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
