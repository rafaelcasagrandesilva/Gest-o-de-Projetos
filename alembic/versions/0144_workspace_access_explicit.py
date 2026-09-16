"""Permissões: o "Acessar" de cada workspace passa a ser EXPLÍCITO.

Antes, `workspace.*.access` era DEDUZIDO: qualquer permissão de um menu do workspace abria o workspace,
e desmarcar "Acessar" na tela de usuários não tinha efeito (ex.: GESTOR sem "Workspace Indicadores"
continuava entrando por `indicators.view` / `company_result.read`). O código novo só reconhece o acesso
CONCEDIDO (perfil ∪ adições − remoções) e bloqueia os recursos exclusivos do workspace sem ele.

Esta migration preserva o acesso de hoje de quem o tinha só por dedução:

1. PERFIS: todo perfil com alguma das permissões que deduziam o workspace (listas CONGELADAS abaixo — a
   união das três cópias da regra antiga: backend de autorização, sessão e frontend, mais a aresta
   agenda → Projetos) recebe o `workspace.*.access` correspondente.
2. USUÁRIOS com adições individuais que deduziam o workspace (e sem linha própria para o código) recebem a
   adição do `workspace.*.access`.
3. USUÁRIOS que ganhariam um workspace que hoje NÃO têm (o perfil passou a tê-lo, mas o usuário removeu
   individualmente todas as permissões que o deduziam) recebem a REMOÇÃO do código — ninguém ganha acesso.

A única perda permitida é a de quem tem o "Acessar" DESMARCADO individualmente (`granted = false`): é
exatamente o que a correção faz valer (decisão de 2026-09-14: respeitar o desmarcado — no backup de
14/09, Jacqueline, Priscilla e Yasmim perdem o workspace Projetos).

VALIDAÇÃO pré/pós (regra do projeto para migrations de permissões): calcula, por usuário e workspace, o
acesso pela regra ANTIGA antes de inserir e pela regra NOVA depois; qualquer diferença fora da perda
permitida aborta a migration (a transação desfaz tudo).

Idempotente (só insere o que falta). downgrade: não remove os códigos (conceder o "Acessar" explícito a
quem já tinha o acesso por dedução é inofensivo sob a regra antiga).

Revision ID: 0144_workspace_access_explicit
Revises: 0143_remove_legacy_debt_payables_instituto
"""

from __future__ import annotations

import logging
from collections import defaultdict

import sqlalchemy as sa
from alembic import op

revision = "0144_workspace_access_explicit"
down_revision = "0143_remove_legacy_debt_payables_instituto"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

_SETTINGS = ("settings.view", "settings.edit", "system.admin")

# Regra ANTIGA congelada: permissões (brutas, já sem as remoções) que deduziam cada workspace.
_DERIVA: dict[str, frozenset[str]] = {
    "workspace.projects.access": frozenset({
        "dashboard.view", "dashboard.director", "projects.view", "projects.view_list", "projects.view_detail",
        "projects.create", "projects.edit", "projects.delete", "employees.view", "employees.edit",
        "vehicles.view", "vehicles.edit", "billing.view", "costs.view", "costs.edit", "reports.view",
        "reports.export", "alerts.view", "users.manage", *_SETTINGS,
        # Aresta do grafo antigo: qualquer permissão da agenda abria Projetos.
        "project_agenda.list", "project_agenda.read", "project_agenda.create",
        "project_agenda.update", "project_agenda.delete",
    }),
    "workspace.finance.access": frozenset({
        "financial_dashboard.read", "payables.view", "payables.edit", "receivables.view", "receivables.edit",
        "invoices.view", "invoices.edit", "debts.view", "debts.edit", "company_finance.view",
        "company_finance.edit", "reports.view", "reports.export", *_SETTINGS,
    }),
    "workspace.assets.access": frozenset({"assets.view", "assets.edit", *_SETTINGS}),
    "workspace.indicators.access": frozenset({"indicators.view", "indicators.director", "company_result.read"}),
    "workspace.legal.access": frozenset({
        "legal_dashboard.read",
        *(f"legal_{r}.{v}" for r in ("cases", "persons", "companies", "projects") for v in ("list", "read", "create", "update", "delete")),
        "legal_imports.list", "legal_imports.create", "legal_reports.read", "legal_reports.export",
    }),
}
_WORKSPACES = tuple(_DERIVA)


def _load(conn):
    perm_ids = dict(conn.execute(sa.text("SELECT name, id FROM permissions")).all())
    role_perms: dict = defaultdict(set)
    for role_id, name in conn.execute(sa.text(
        "SELECT rp.role_id, p.name FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id"
    )).all():
        role_perms[role_id].add(name)
    user_roles: dict = defaultdict(set)
    for user_id, role_id in conn.execute(sa.text("SELECT user_id, role_id FROM user_roles")).all():
        user_roles[user_id].add(role_id)
    adds: dict = defaultdict(set)
    removes: dict = defaultdict(set)
    for user_id, name, granted in conn.execute(sa.text(
        "SELECT up.user_id, p.name, up.granted FROM user_permissions up JOIN permissions p ON p.id = up.permission_id"
    )).all():
        (adds if granted else removes)[user_id].add(name)
    users = [u for (u,) in conn.execute(sa.text("SELECT id FROM users")).all()]
    return perm_ids, role_perms, user_roles, adds, removes, users


def _base(user_id, role_perms, user_roles, adds) -> set[str]:
    out: set[str] = set(adds[user_id])
    for role_id in user_roles[user_id]:
        out |= role_perms[role_id]
    return out


def _acesso_antigo(user_id, role_perms, user_roles, adds, removes) -> set[str]:
    efetivo = _base(user_id, role_perms, user_roles, adds) - removes[user_id]
    return {ws for ws in _WORKSPACES if ws in efetivo or efetivo & _DERIVA[ws]}


def _acesso_novo(user_id, role_perms, user_roles, adds, removes) -> set[str]:
    efetivo = _base(user_id, role_perms, user_roles, adds) - removes[user_id]
    return {ws for ws in _WORKSPACES if ws in efetivo}


def upgrade() -> None:
    conn = op.get_bind()
    perm_ids, role_perms, user_roles, adds, removes, users = _load(conn)
    missing = [ws for ws in _WORKSPACES if ws not in perm_ids]
    if missing:
        raise RuntimeError(f"0144: códigos de workspace ausentes em permissions: {missing}")

    antes = {u: _acesso_antigo(u, role_perms, user_roles, adds, removes) for u in users}

    # 1. Perfis.
    perfis = 0
    for role_id, names in list(role_perms.items()):
        for ws in _WORKSPACES:
            if ws not in names and names & _DERIVA[ws]:
                conn.execute(sa.text(
                    "INSERT INTO role_permissions (id, created_at, updated_at, role_id, permission_id) "
                    "VALUES (gen_random_uuid(), now(), now(), :r, :p)"
                ), {"r": role_id, "p": perm_ids[ws]})
                names.add(ws)
                perfis += 1

    # 2 e 3. Usuários.
    adicoes = remocoes = 0
    for u in users:
        for ws in _WORKSPACES:
            if ws in adds[u] or ws in removes[u]:
                continue  # o usuário já tem linha própria para o código: vale a escolha dele
            efetivo_novo = _base(u, role_perms, user_roles, adds) - removes[u]
            tinha = ws in antes[u]
            teria = ws in efetivo_novo
            if tinha and not teria:
                conn.execute(sa.text(
                    "INSERT INTO user_permissions (id, created_at, updated_at, user_id, permission_id, granted) "
                    "VALUES (gen_random_uuid(), now(), now(), :u, :p, true)"
                ), {"u": u, "p": perm_ids[ws]})
                adds[u].add(ws)
                adicoes += 1
            elif teria and not tinha:
                conn.execute(sa.text(
                    "INSERT INTO user_permissions (id, created_at, updated_at, user_id, permission_id, granted) "
                    "VALUES (gen_random_uuid(), now(), now(), :u, :p, false)"
                ), {"u": u, "p": perm_ids[ws]})
                removes[u].add(ws)
                remocoes += 1

    # Validação: só perde quem tem o "Acessar" desmarcado individualmente; ninguém ganha.
    perdas_permitidas = []
    for u in users:
        depois = _acesso_novo(u, role_perms, user_roles, adds, removes)
        ganhou = depois - antes[u]
        perdeu = antes[u] - depois
        indevidas = {ws for ws in perdeu if ws not in removes[u]}
        if ganhou or indevidas:
            raise RuntimeError(f"0144: acesso mudaria para o usuário {u}: ganhou={sorted(ganhou)} perdeu={sorted(indevidas)}")
        perdas_permitidas += [(u, ws) for ws in perdeu]

    log.info(
        "0144: perfis +%d acessos; usuários +%d adições, +%d remoções; perdas pelo \"Acessar\" desmarcado: %d %s",
        perfis, adicoes, remocoes, len(perdas_permitidas), perdas_permitidas,
    )


def downgrade() -> None:
    # Não remove: sob a regra antiga o acesso explícito é equivalente ao deduzido.
    pass
