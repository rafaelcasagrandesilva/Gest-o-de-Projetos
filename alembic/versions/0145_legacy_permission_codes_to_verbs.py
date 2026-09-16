"""Permissões: códigos legados `.view/.edit` viram os códigos de verbo equivalentes.

Os aliases legados (`payables.view`, `employees.edit`, `projects.view_list`…) ficavam OCULTOS na tela de
permissões e só existiam no banco; quem os tinha via as caixas de verbo desmarcadas mesmo tendo o acesso
(o legado concedia pelo grafo). A tela nova, em blocos por workspace, mostra só os verbos — então cada
legado é trocado pelo FECHO que ele concedia (tabela CONGELADA abaixo, calculada do grafo em 2026-09-14).

1. PERFIS: recebem os verbos do fecho de cada legado que tinham; as linhas legadas saem.
2. USUÁRIOS: adições legadas viram adições dos verbos; remoções legadas saem (o efeito é recalculado).
3. RECONCILIAÇÃO por usuário: o efetivo EXPANDIDO depois tem de ser igual ao de antes (ignorando os
   próprios códigos legados). Verbo que sobrar vira remoção individual; verbo que faltar volta pela
   retirada de uma remoção individual ou por adição.

Os códigos continuam no catálogo e as arestas do grafo continuam valendo (nada no código checa legado
deixa de funcionar); só não há mais quem os tenha. `system.admin`, `projects.create/delete`,
`projects.documents.*`, `*.director`, `reports.export`, `users.manage`, workspaces e códigos de concessão
explícita não são legados e não mudam.

VALIDAÇÃO pré/pós por usuário (regra do projeto para migrations de permissões): qualquer diferença aborta.

Revision ID: 0145_legacy_permission_codes_to_verbs
Revises: 0144_workspace_access_explicit
"""

from __future__ import annotations

import logging
from collections import defaultdict

import sqlalchemy as sa
from alembic import op

from app.core.permission_codes import expand_permissions

revision = "0145_legacy_permission_codes_to_verbs"
down_revision = "0144_workspace_access_explicit"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

_CC = "cost_center.reference"


def _crud(r: str) -> tuple[list[str], list[str]]:
    view = [f"{r}.list", f"{r}.read", f"{r}.sensitive"]
    return view, [*view, f"{r}.create", f"{r}.update", f"{r}.delete"]


# Legado → verbos que ele concedia (fecho do grafo, sem os próprios legados). CONGELADO.
_VERBOS: dict[str, list[str]] = {
    "dashboard.view": ["dashboard.read", "dashboard.sensitive"],
    "indicators.view": ["indicators.read", "indicators.sensitive"],
    "projects.view": [_CC, "projects.reference", "projects.list", "projects.read", "projects.sensitive"],
    "projects.view_list": [_CC],
    "projects.view_detail": [],
    "projects.edit": [_CC, "projects.reference", "projects.list", "projects.read", "projects.sensitive", "projects.update"],
    "employees.view": [_CC, "employees.reference", "employees.list", "employees.read", "employees.sensitive", "employees.export"],
    "employees.edit": [
        _CC, "employees.reference", "employees.list", "employees.read", "employees.sensitive", "employees.export",
        "employees.create", "employees.update", "employees.delete",
    ],
    "vehicles.view": [_CC, "vehicles.reference", "vehicles.list", "vehicles.read", "vehicles.sensitive", "vehicles.export"],
    "vehicles.edit": [
        _CC, "vehicles.reference", "vehicles.list", "vehicles.read", "vehicles.sensitive", "vehicles.export",
        "vehicles.create", "vehicles.update", "vehicles.delete",
    ],
    "assets.view": [_CC, "assets.reference", "assets.list", "assets.read", "assets.sensitive"],
    "assets.edit": [_CC, "assets.reference", "assets.list", "assets.read", "assets.sensitive", "assets.create", "assets.update", "assets.delete"],
    "billing.view": _crud("billing")[0],
    "settings.view": ["settings.read"],
    "settings.edit": ["settings.read", "settings.update"],
    "reports.view": ["reports.read"],
    "alerts.view": ["alerts.read"],
}
for _r in ("payables", "receivables", "invoices", "debts", "costs"):
    _VERBOS[f"{_r}.view"], _VERBOS[f"{_r}.edit"] = _crud(_r)
_VERBOS["company_finance.view"] = [*_crud("company_finance")[0], _CC]
_VERBOS["company_finance.edit"] = _crud("company_finance")[1]

_LEGADOS = frozenset(_VERBOS)


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


def _base(u, role_perms, user_roles, adds) -> set[str]:
    out = set(adds[u])
    for role_id in user_roles[u]:
        out |= role_perms[role_id]
    return out


def _efetivo(u, role_perms, user_roles, adds, removes) -> set[str]:
    return set(expand_permissions(_base(u, role_perms, user_roles, adds) - removes[u])) - _LEGADOS


def upgrade() -> None:
    conn = op.get_bind()
    perm_ids, role_perms, user_roles, adds, removes, users = _load(conn)
    faltando = sorted({v for vs in _VERBOS.values() for v in vs} - set(perm_ids))
    if faltando:
        raise RuntimeError(f"0145: códigos de verbo ausentes em permissions: {faltando}")

    antes = {u: _efetivo(u, role_perms, user_roles, adds, removes) for u in users}
    legados = sorted(_LEGADOS)

    def add_role(role_id, name):
        conn.execute(sa.text(
            "INSERT INTO role_permissions (id, created_at, updated_at, role_id, permission_id) "
            "VALUES (gen_random_uuid(), now(), now(), :r, :p)"
        ), {"r": role_id, "p": perm_ids[name]})
        role_perms[role_id].add(name)

    def set_user(u, name, granted: bool):
        conn.execute(sa.text("DELETE FROM user_permissions WHERE user_id = :u AND permission_id = :p"), {"u": u, "p": perm_ids[name]})
        adds[u].discard(name)
        removes[u].discard(name)
        conn.execute(sa.text(
            "INSERT INTO user_permissions (id, created_at, updated_at, user_id, permission_id, granted) "
            "VALUES (gen_random_uuid(), now(), now(), :u, :p, :g)"
        ), {"u": u, "p": perm_ids[name], "g": granted})
        (adds if granted else removes)[u].add(name)

    def clear_user(u, name):
        conn.execute(sa.text("DELETE FROM user_permissions WHERE user_id = :u AND permission_id = :p"), {"u": u, "p": perm_ids[name]})
        adds[u].discard(name)
        removes[u].discard(name)

    # 1. Perfis.
    perfis = 0
    for role_id, names in list(role_perms.items()):
        for legado in names & _LEGADOS:
            for verbo in _VERBOS[legado]:
                if verbo not in names:
                    add_role(role_id, verbo)
                    perfis += 1
        names -= _LEGADOS
    conn.execute(sa.text(
        "DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE name = ANY(:names))"
    ), {"names": legados})

    # 2. Usuários: adições legadas viram adições dos verbos (sem sobrescrever linha própria do usuário).
    for u in users:
        for legado in adds[u] & _LEGADOS:
            for verbo in _VERBOS[legado]:
                if verbo not in adds[u] and verbo not in removes[u]:
                    set_user(u, verbo, True)
        adds[u] -= _LEGADOS
        removes[u] -= _LEGADOS
    conn.execute(sa.text(
        "DELETE FROM user_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE name = ANY(:names))"
    ), {"names": legados})

    # 3. Reconciliação por usuário.
    sobras = faltas = 0
    for u in users:
        for _ in range(3):
            depois = _efetivo(u, role_perms, user_roles, adds, removes)
            if depois == antes[u]:
                break
            raw = _base(u, role_perms, user_roles, adds) - removes[u]
            for code in sorted(raw - antes[u]):
                set_user(u, code, False)
                sobras += 1
            for code in sorted(antes[u] - depois):
                if code not in perm_ids:
                    continue  # implicado pelo grafo, sem linha no catálogo — vem pelo código que o implica
                faltas += 1
                if code in removes[u]:
                    clear_user(u, code)
                if code not in _base(u, role_perms, user_roles, adds):
                    set_user(u, code, True)

    for u in users:
        depois = _efetivo(u, role_perms, user_roles, adds, removes)
        if depois != antes[u]:
            raise RuntimeError(
                f"0145: efetivo mudaria para o usuário {u}: ganhou={sorted(depois - antes[u])} perdeu={sorted(antes[u] - depois)}"
            )

    log.info("0145: perfis +%d verbos; reconciliação: %d remoções, %d restituições", perfis, sobras, faltas)


def downgrade() -> None:
    # Não reverte: os verbos concedem exatamente o que os legados concediam.
    pass
