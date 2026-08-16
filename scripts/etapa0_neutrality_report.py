"""Relatório de neutralidade da Etapa 0 (modelo de permissões por verbos).

Compara, para TODOS os usuários do banco de desenvolvimento, o resolvedor de permissões ANTIGO
(congelado abaixo, idêntico ao app/api/deps.py pré-Etapa 0) contra o NOVO `user_has_permission`.
Certifica que nenhum usuário ganhou/perdeu capacidade sobre os códigos LEGADOS (enforçados), e que
os códigos NOVOS não vazam para a sessão do frontend.

Uso:
    python -m scripts.etapa0_neutrality_report

Não altera nada no banco (somente leitura).
"""

from __future__ import annotations

import asyncio

from app.api.deps import is_app_superuser, user_has_permission
from app.core import permission_codes as pc
from app.core.permission_codes import (
    ACTIVE_PERMISSION_CODES,
    EXPLICIT_GRANT_ONLY_PERMISSIONS,
    NEW_PERMISSION_CODES,
    SYSTEM_ADMIN,
    WORKSPACE_ASSETS_ACCESS,
    WORKSPACE_FINANCE_ACCESS,
    WORKSPACE_INDICATORS_ACCESS,
    WORKSPACE_PROJECTS_ACCESS,
)
from app.core.session_context import session_permission_names
from app.database.session import AsyncSessionLocal
from app.repositories.users import UserRepository

# Conjuntos de derivação de workspace EXATAMENTE como em app/api/deps.py (oráculo do comportamento antigo).
_DEPS_PROJECTS = {
    pc.DASHBOARD_VIEW, pc.DASHBOARD_DIRECTOR, pc.PROJECTS_VIEW, pc.PROJECTS_VIEW_LIST,
    pc.PROJECTS_VIEW_DETAIL, pc.PROJECTS_CREATE, pc.PROJECTS_EDIT, pc.PROJECTS_DELETE,
    pc.EMPLOYEES_VIEW, pc.EMPLOYEES_EDIT, pc.VEHICLES_VIEW, pc.VEHICLES_EDIT, pc.BILLING_VIEW,
    pc.COSTS_VIEW, pc.COSTS_EDIT, pc.REPORTS_VIEW, pc.REPORTS_EXPORT, pc.ALERTS_VIEW,
    pc.SETTINGS_VIEW, pc.SETTINGS_EDIT, pc.USERS_MANAGE,
}
_DEPS_FINANCE = {
    pc.PAYABLES_VIEW, pc.PAYABLES_EDIT, pc.RECEIVABLES_VIEW, pc.RECEIVABLES_EDIT, pc.INVOICES_VIEW,
    pc.INVOICES_EDIT, pc.DEBTS_VIEW, pc.DEBTS_EDIT, pc.COMPANY_FINANCE_VIEW, pc.COMPANY_FINANCE_EDIT,
    pc.REPORTS_VIEW, pc.REPORTS_EXPORT, pc.SETTINGS_VIEW, pc.SETTINGS_EDIT,
}
_DEPS_ASSETS = {pc.ASSETS_VIEW, pc.ASSETS_EDIT, pc.SETTINGS_VIEW, pc.SETTINGS_EDIT}
_DEPS_INDICATORS = {pc.INDICATORS_VIEW, pc.INDICATORS_DIRECTOR}


def _role_names(user) -> set[str]:
    return {l.role.name for l in (user.roles or []) if getattr(l, "role", None)}


def _effective(user) -> set[str]:
    adds, removes = set(), set()
    for up in user.user_permissions or []:
        if not up.permission:
            continue
        (removes if getattr(up, "granted", True) is False else adds).add(up.permission.name)
    role_perms: set[str] = set()
    for l in user.roles or []:
        for rp in getattr(l.role, "permissions", []) or []:
            if rp.permission:
                role_perms.add(rp.permission.name)
    return (role_perms | adds) - removes


def _legacy_has(user, code: str) -> bool:
    """Resolvedor ANTIGO congelado (app/api/deps.py pré-Etapa 0)."""
    if code in EXPLICIT_GRANT_ONLY_PERMISSIONS:
        return code in {up.permission.name for up in user.user_permissions or []
                        if up.permission and getattr(up, "granted", True) is not False}
    if is_app_superuser(user):
        return True
    if "ADMIN" in _role_names(user):
        return True
    names = _effective(user)
    if SYSTEM_ADMIN in names:
        return True
    if code in names:
        return True
    if code in (pc.PROJECTS_VIEW_LIST, pc.PROJECTS_VIEW_DETAIL) and pc.PROJECTS_VIEW in names:
        return True
    if code == WORKSPACE_PROJECTS_ACCESS and names & _DEPS_PROJECTS:
        return True
    if code == WORKSPACE_FINANCE_ACCESS and names & _DEPS_FINANCE:
        return True
    if code == WORKSPACE_ASSETS_ACCESS and names & _DEPS_ASSETS:
        return True
    if code == WORKSPACE_INDICATORS_ACCESS and names & _DEPS_INDICATORS:
        return True
    return False


async def main() -> int:
    # Neutralidade vale para os códigos LEGADOS (independe de quais novos já foram ativados).
    legacy = sorted(set(pc.ALL_PERMISSION_CODES) - set(NEW_PERMISSION_CODES))
    codes = legacy + [
        WORKSPACE_PROJECTS_ACCESS, WORKSPACE_FINANCE_ACCESS,
        WORKSPACE_ASSETS_ACCESS, WORKSPACE_INDICATORS_ACCESS,
    ]
    # Vazamento: só os códigos novos AINDA INATIVOS não podem aparecer na sessão.
    inactive_new = set(NEW_PERMISSION_CODES) - set(ACTIVE_PERMISSION_CODES)
    cap_diffs: list[tuple] = []
    leak_diffs: list[tuple] = []
    n_users = 0

    async with AsyncSessionLocal() as db:
        users = await UserRepository(db).list(offset=0, limit=100000, include_deleted=True)
        for u in users:
            n_users += 1
            for code in codes:
                if _legacy_has(u, code) != user_has_permission(u, code):
                    cap_diffs.append((u.email, code, _legacy_has(u, code), user_has_permission(u, code)))
            leaked = set(session_permission_names(u, is_superuser=is_app_superuser(u))) & inactive_new
            if leaked:
                leak_diffs.append((u.email, sorted(leaked)))

    print("=" * 72)
    print("RELATÓRIO DE NEUTRALIDADE — Etapa 0 (modelo de permissões por verbos)")
    print("=" * 72)
    print(f"Banco de dev · usuários avaliados: {n_users}")
    print(f"Códigos legados/workspace comparados por usuário: {len(codes)}")
    print()
    print(f"[A] Capacidade (antigo vs novo) sobre códigos LEGADOS ....... "
          f"{'OK — 0 divergências' if not cap_diffs else f'FALHA — {len(cap_diffs)} divergências'}")
    for d in cap_diffs[:50]:
        print(f"     - {d[0]} | {d[1]} | antigo={d[2]} novo={d[3]}")
    print(f"[B] Vazamento de códigos NOVOS na sessão do frontend ........ "
          f"{'OK — nenhum vazamento' if not leak_diffs else f'FALHA — {len(leak_diffs)} usuários'}")
    for d in leak_diffs[:50]:
        print(f"     - {d[0]} | {d[1]}")
    print()
    ok = not cap_diffs and not leak_diffs
    print("RESULTADO:", "APROVADO — nenhum usuário ganhou ou perdeu capacidade." if ok
          else "REPROVADO — ver divergências acima.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
