"""Isolamento de permissões por módulo: cria payables.edit/receivables.edit e preserva o acesso
atual dos usuários com grants customizados (sem regressão).

Contexto: até aqui alguns módulos dependiam da permissão de outro:
- CAP (Contas a Pagar) editava com `costs.edit` (Custos)               -> agora `payables.edit`.
- Endividamento lia/editava via `company_finance.view/edit`            -> agora `debts.view/edit`.
- Contas a Receber (itens manuais) editava com `invoices.edit`         -> agora `receivables.edit`.

Usuários cujas permissões vêm do PRESET da role (sem linhas em `user_permissions`) são resolvidos
em runtime pelo código (ROLE_PRESET já atualizado) — não precisam de migration. Já os usuários com
permissões CUSTOMIZADAS têm o conjunto congelado em `user_permissions`; para eles, esta migration
concede aditivamente a permissão específica equivalente à que eles já possuíam, preservando
exatamente o acesso que tinham antes.

Propriedades:
- ADITIVA e idempotente: só cria o que falta; rodar de novo não duplica (ON CONFLICT / NOT EXISTS).
- Nunca remove permissões (sem regressão).
- Downgrade no-op (conservador, como a 0088): não dá para distinguir grants concedidos por esta
  migration dos concedidos manualmente depois; reverter poderia apagar acessos legítimos.

Revision ID: 0090_decouple_module_permissions
Revises: 0089_cost_center_history
"""

from __future__ import annotations

from alembic import op

revision = "0090_decouple_module_permissions"
down_revision = "0089_cost_center_history"
branch_labels = None
depends_on = None


# (permissão de origem já existente) -> (permissão específica do módulo a conceder)
_COMPAT_GRANTS: tuple[tuple[str, str], ...] = (
    ("costs.edit", "payables.edit"),            # CAP: edição própria
    ("company_finance.view", "debts.view"),     # Endividamento: leitura própria
    ("company_finance.edit", "debts.edit"),     # Endividamento: edição própria
    ("invoices.edit", "receivables.edit"),      # Contas a Receber (manuais): edição própria
)

_NEW_PERMISSION_NAMES: tuple[str, ...] = ("payables.edit", "receivables.edit")


def upgrade() -> None:
    # 1) Garante que os novos códigos existam na tabela `permissions` (idempotente).
    for name in _NEW_PERMISSION_NAMES:
        op.execute(
            f"""
            INSERT INTO permissions (id, created_at, updated_at, name)
            VALUES (gen_random_uuid(), now(), now(), '{name}')
            ON CONFLICT (name) DO NOTHING;
            """
        )

    # 2) Backfill aditivo dos grants para usuários com permissões customizadas.
    for old_name, new_name in _COMPAT_GRANTS:
        op.execute(
            f"""
            INSERT INTO user_permissions (id, created_at, updated_at, user_id, permission_id)
            SELECT gen_random_uuid(), now(), now(), up.user_id, new_p.id
              FROM user_permissions up
              JOIN permissions old_p ON old_p.id = up.permission_id AND old_p.name = '{old_name}'
              JOIN permissions new_p ON new_p.name = '{new_name}'
             WHERE NOT EXISTS (
                       SELECT 1 FROM user_permissions ux
                        WHERE ux.user_id = up.user_id
                          AND ux.permission_id = new_p.id
                   );
            """
        )


def downgrade() -> None:
    # No-op intencional: migration aditiva de compatibilidade. Não removemos grants para não
    # apagar acessos legítimos (inclusive concedidos manualmente após o deploy).
    pass
