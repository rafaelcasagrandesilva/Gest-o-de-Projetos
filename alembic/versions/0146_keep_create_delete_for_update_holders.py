"""Permissões: quem só tinha "Editar" no Contas a pagar / Notas fiscais mantém incluir e excluir.

Até aqui os endpoints de incluir despesa avulsa, excluir despesa (individual e em massa) e excluir NF
exigiam `payables.update` / `invoices.update`. A correção passou a exigir os verbos próprios
(`*.create` / `*.delete`). Quem tinha Editar sem Criar/Excluir perderia essas ações — decisão de
2026-09-14: MANTER como hoje (no backup de 14/09, só João Carlos Martins, GESTOR com Editar individual).

Regra (sem nome de usuário): para cada usuário cujo efetivo concede `<r>.update` (com o "Acessar" do
Financeiro), concede individualmente `<r>.create` e `<r>.delete` que ainda não tiver. Quem DESMARCOU
Criar/Excluir individualmente (`granted = false`) fica como está — foi escolha explícita.

Idempotente. downgrade: não remove (as ações já eram possíveis antes da correção).

Revision ID: 0146_keep_create_delete_for_update_holders
Revises: 0145_legacy_permission_codes_to_verbs
"""

from __future__ import annotations

import logging
from collections import defaultdict

import sqlalchemy as sa
from alembic import op

from app.core.permission_codes import expand_permissions, workspace_required_for

revision = "0146_keep_create_delete_for_update_holders"
down_revision = "0145_legacy_permission_codes_to_verbs"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

_RECURSOS = ("payables", "invoices")


def _has(efetivo: set[str], code: str) -> bool:
    ws = workspace_required_for(code)
    return code in efetivo and (ws is None or ws in efetivo)


def upgrade() -> None:
    conn = op.get_bind()
    perm_ids = dict(conn.execute(sa.text("SELECT name, id FROM permissions")).all())
    base: dict = defaultdict(set)
    for user_id, name in conn.execute(sa.text(
        "SELECT ur.user_id, p.name FROM user_roles ur "
        "JOIN role_permissions rp ON rp.role_id = ur.role_id JOIN permissions p ON p.id = rp.permission_id"
    )).all():
        base[user_id].add(name)
    removes: dict = defaultdict(set)
    for user_id, name, granted in conn.execute(sa.text(
        "SELECT up.user_id, p.name, up.granted FROM user_permissions up JOIN permissions p ON p.id = up.permission_id"
    )).all():
        (base[user_id].add(name) if granted else removes[user_id].add(name))

    concedidos = []
    for (user_id,) in conn.execute(sa.text("SELECT id FROM users")).all():
        efetivo = set(expand_permissions(base[user_id] - removes[user_id]))
        for r in _RECURSOS:
            if not _has(efetivo, f"{r}.update"):
                continue
            for verbo in ("create", "delete"):
                code = f"{r}.{verbo}"
                if _has(efetivo, code) or code in removes[user_id]:
                    continue
                if code not in perm_ids:
                    raise RuntimeError(f"0146: código ausente em permissions: {code}")
                conn.execute(sa.text(
                    "INSERT INTO user_permissions (id, created_at, updated_at, user_id, permission_id, granted) "
                    "VALUES (gen_random_uuid(), now(), now(), :u, :p, true)"
                ), {"u": user_id, "p": perm_ids[code]})
                concedidos.append((user_id, code))

    log.info("0146: %d concessões individuais de criar/excluir: %s", len(concedidos), concedidos)


def downgrade() -> None:
    pass
