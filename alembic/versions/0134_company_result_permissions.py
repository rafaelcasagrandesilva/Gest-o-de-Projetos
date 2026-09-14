"""Dados Sensíveis — RESULTADO DA EMPRESA: recurso próprio. Exclusivamente ADITIVA.

Cadastra os códigos `company_result.read` (acesso ao painel Indicadores → Resultado da Empresa) e
`company_result.sensitive` (receber os valores) em `permissions` e os adiciona aos perfis que devem
enxergar o painel desde o primeiro dia.

Recurso PRÓPRIO, no mesmo padrão da 0098 (Dashboard Financeiro): não existe caminho no grafo
(`PERMISSION_IMPLIES`) até `company_result.read`, então o acesso inicial precisa ser SEMEADO nos perfis.
Como o painel cruza Indicadores com Custos Indiretos (Finanças da empresa), a regra de semeadura é:

  * perfil (de sistema OU custom) que tenha ao menos um código de Indicadores
    (indicators.view / indicators.director / indicators.read)
    E ao menos um código de Finanças da empresa
    (company_finance.view / edit / read / create / update / delete);
  * UNIÃO todo perfil que tenha `system.admin`.

Semeia `read` + `sensitive` (mantém a visibilidade dos valores, como na 0098). A partir daqui um admin
pode REMOVER `company_result.sensitive` (no perfil ou por delta) para ocultar só os valores.

Validação do efetivo pré/pós (regra do projeto para migrations de permissões): antes de inserir,
calcula o conjunto de perfis esperado; depois de inserir, confere que TODO perfil esperado tem os dois
códigos e que NENHUM perfil fora do conjunto os recebeu. Qualquer divergência aborta a migration.

Puramente ADITIVA: nada é removido; nenhum `user_permissions` é tocado; idempotente
(ON CONFLICT DO NOTHING).

Revision ID: 0134_company_result_permissions
Revises: 0133_anticipation_mode
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0134_company_result_permissions"
down_revision = "0133_anticipation_mode"
branch_labels = None
depends_on = None

_NEW_CODES: tuple[str, ...] = ("company_result.read", "company_result.sensitive")

# Qualquer um destes = o perfil já enxerga Indicadores.
_INDICATORS_CODES: tuple[str, ...] = ("indicators.view", "indicators.director", "indicators.read")

# Qualquer um destes = o perfil já enxerga Finanças da empresa (Custos Indiretos).
# company_finance.list NÃO entra (list < read), no mesmo critério da 0098.
_COMPANY_FINANCE_CODES: tuple[str, ...] = (
    "company_finance.view", "company_finance.edit", "company_finance.read",
    "company_finance.create", "company_finance.update", "company_finance.delete",
)

_ADMIN_CODE = "system.admin"

# Perfis que a regra concede (calculado sobre o estado ANTES da inserção).
_EXPECTED_ROLES_SQL = (
    "SELECT r.id FROM roles r "
    " WHERE ( EXISTS (SELECT 1 FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id "
    "                  WHERE rp.role_id = r.id AND p.name = ANY(:indicators)) "
    "     AND EXISTS (SELECT 1 FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id "
    "                  WHERE rp.role_id = r.id AND p.name = ANY(:company_finance)) ) "
    "    OR EXISTS (SELECT 1 FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id "
    "                WHERE rp.role_id = r.id AND p.name = :admin)"
)

_RULE_PARAMS = {
    "indicators": list(_INDICATORS_CODES),
    "company_finance": list(_COMPANY_FINANCE_CODES),
    "admin": _ADMIN_CODE,
}


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

    # PRÉ: conjunto esperado pela regra (antes de qualquer vínculo novo).
    expected = {row[0] for row in conn.execute(sa.text(_EXPECTED_ROLES_SQL), _RULE_PARAMS)}

    # Perfis que JÁ tinham algum dos códigos (re-execução idempotente / concessão manual prévia):
    # não são contados como "vazamento" da regra, pois esta migration não os criou.
    preexisting = {
        row[0]
        for row in conn.execute(
            sa.text(
                "SELECT DISTINCT rp.role_id FROM role_permissions rp "
                "  JOIN permissions p ON p.id = rp.permission_id AND p.name = ANY(:names)"
            ),
            {"names": list(_NEW_CODES)},
        )
    }

    for pname in _NEW_CODES:
        conn.execute(
            sa.text(
                "INSERT INTO role_permissions (id, created_at, updated_at, role_id, permission_id) "
                "SELECT gen_random_uuid(), now(), now(), e.id, np.id "
                f"  FROM ({_EXPECTED_ROLES_SQL}) e "
                "  JOIN permissions np ON np.name = :new "
                "ON CONFLICT (role_id, permission_id) DO NOTHING"
            ),
            {**_RULE_PARAMS, "new": pname},
        )
    # user_permissions: intocada (por design).

    # PÓS: todo perfil esperado tem os DOIS códigos; nenhum perfil fora do conjunto os recebeu.
    holders: dict[str, set] = {}
    for pname in _NEW_CODES:
        holders[pname] = {
            row[0]
            for row in conn.execute(
                sa.text(
                    "SELECT rp.role_id FROM role_permissions rp "
                    "  JOIN permissions p ON p.id = rp.permission_id AND p.name = :n"
                ),
                {"n": pname},
            )
        }
        missing = expected - holders[pname]
        if missing:
            raise RuntimeError(
                f"0134: perfis esperados sem {pname}: {sorted(str(r) for r in missing)}"
            )
        leaked = holders[pname] - expected - preexisting
        if leaked:
            raise RuntimeError(
                f"0134: perfis FORA da regra receberam {pname}: {sorted(str(r) for r in leaked)}"
            )


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
