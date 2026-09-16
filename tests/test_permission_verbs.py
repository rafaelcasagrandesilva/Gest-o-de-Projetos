"""Etapa 0 — modelo de permissões por verbos.

Cobre (a) as implicações do grafo e (b) a NEUTRALIDADE: nenhum código LEGADO muda de resultado por
causa da nova infraestrutura. O teste-ouro reimplementa o resolvedor ANTIGO e compara, código a
código legado, contra o `user_has_permission` real — para uma matriz de usuários representativos.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.api.deps import user_has_permission
from app.core import permission_codes as pc
from app.core.permission_codes import (
    ACTIVE_PERMISSION_CODES,
    EXPLICIT_GRANT_ONLY_PERMISSIONS,
    PRESET_CONSULTA,
    PRESET_GESTOR,
    PROJECTS_VIEW,
    PROJECTS_VIEW_DETAIL,
    PROJECTS_VIEW_LIST,
    SYSTEM_ADMIN,
    WORKSPACE_ASSETS_ACCESS,
    WORKSPACE_FINANCE_ACCESS,
    WORKSPACE_INDICATORS_ACCESS,
    WORKSPACE_PROJECTS_ACCESS,
    expand_permissions,
)
_SUPERUSER_EMAIL = "rafael.casagrande@meconsulting.com.br"

# Conjunto LEGADO congelado (independe de quais códigos novos já foram ativados por etapa):
# a neutralidade vale para os códigos que existiam ANTES do modelo de verbos.
_LEGACY_CODES = sorted(set(pc.ALL_PERMISSION_CODES) - set(pc.NEW_PERMISSION_CODES))

def _user(
    *perms: str,
    email: str = "verbs-test@example.com",
    roles: list[str] | None = None,
    removes: tuple[str, ...] = (),
) -> SimpleNamespace:
    """Usuário com adições individuais (user_permissions), remoções (granted=False) e, opcionalmente,
    perfis por nome. Para perfis, materializa role.permissions com o preset correspondente.
    """
    ups = [SimpleNamespace(permission=SimpleNamespace(name=p), granted=True) for p in perms]
    ups += [SimpleNamespace(permission=SimpleNamespace(name=p), granted=False) for p in removes]
    role_links = []
    for rn in roles or []:
        preset = pc.ROLE_PRESET.get(rn, frozenset())
        rp = [SimpleNamespace(permission=SimpleNamespace(name=p)) for p in preset]
        role_links.append(SimpleNamespace(role=SimpleNamespace(name=rn, permissions=rp)))
    return SimpleNamespace(email=email, user_permissions=ups, roles=role_links, is_active=True)


# --- Oráculo do resolvedor: replica app/api/deps.user_has_permission SEM atalhos de perfil.
# Acesso vem só das permissões (fecho do grafo). Workspace só quando CONCEDIDO (sem dedução pelos menus)
# e recurso exclusivo de workspace exige o acesso a ele. Sem ROLE ADMIN, sem e-mail superusuário, sem
# system.admin liberando negócio (system.admin só implica funcionalidades de sistema).
def _legacy_effective(user: SimpleNamespace) -> set[str]:
    adds = {up.permission.name for up in user.user_permissions if getattr(up, "granted", True) is not False}
    removes = {up.permission.name for up in user.user_permissions if getattr(up, "granted", True) is False}
    role_perms: set[str] = set()
    for link in user.roles or []:
        for rp in getattr(link.role, "permissions", []) or []:
            role_perms.add(rp.permission.name)
    return (role_perms | adds) - removes


def _legacy_has(user: SimpleNamespace, code: str) -> bool:
    names = expand_permissions(_legacy_effective(user))
    if code in EXPLICIT_GRANT_ONLY_PERMISSIONS:
        granted = code in {up.permission.name for up in user.user_permissions if getattr(up, "granted", True) is not False}
    else:
        granted = code in names
    if not granted:
        return False
    workspace = pc.workspace_required_for(code)
    return workspace is None or workspace in names


class WorkspaceAccessTests(unittest.TestCase):
    """"Acessar" do workspace manda: só vale concedido e bloqueia os recursos exclusivos dele."""

    def test_menus_do_not_grant_workspace(self):
        u = _user(pc.INDICATORS_VIEW, pc.INDICATORS_DIRECTOR, pc.COMPANY_RESULT_READ)
        self.assertFalse(user_has_permission(u, WORKSPACE_INDICATORS_ACCESS))
        u = _user(pc.PAYABLES_VIEW, pc.SETTINGS_EDIT, pc.REPORTS_VIEW)
        self.assertFalse(user_has_permission(u, WORKSPACE_FINANCE_ACCESS))
        self.assertFalse(user_has_permission(u, WORKSPACE_ASSETS_ACCESS))
        # Agenda deixou de abrir o workspace Projetos pelo grafo.
        self.assertFalse(user_has_permission(_user(pc.PROJECT_AGENDA_UPDATE), WORKSPACE_PROJECTS_ACCESS))

    def test_exclusive_resources_require_workspace(self):
        sem = _user(pc.PAYABLES_READ, pc.COMPANY_RESULT_READ, pc.PROJECT_AGENDA_LIST, pc.DASHBOARD_READ)
        for code in (pc.PAYABLES_READ, pc.COMPANY_RESULT_READ, pc.PROJECT_AGENDA_LIST, pc.DASHBOARD_READ):
            self.assertFalse(user_has_permission(sem, code), f"{code} sem o workspace não vale")
        com = _user(
            pc.PAYABLES_READ, pc.COMPANY_RESULT_READ, pc.PROJECT_AGENDA_LIST, pc.DASHBOARD_READ,
            WORKSPACE_FINANCE_ACCESS, WORKSPACE_INDICATORS_ACCESS, WORKSPACE_PROJECTS_ACCESS,
        )
        for code in (pc.PAYABLES_READ, pc.COMPANY_RESULT_READ, pc.PROJECT_AGENDA_LIST, pc.DASHBOARD_READ):
            self.assertTrue(user_has_permission(com, code), f"{code} com o workspace vale")

    def test_shared_lookups_do_not_require_workspace(self):
        # Cadastros usados em mais de um workspace (combos do Financeiro) seguem só pela permissão.
        u = _user(pc.PROJECTS_LIST, pc.EMPLOYEES_READ, pc.VEHICLES_READ, pc.SETTINGS_READ)
        for code in (pc.PROJECTS_LIST, pc.EMPLOYEES_READ, pc.VEHICLES_READ, pc.SETTINGS_READ):
            self.assertTrue(user_has_permission(u, code))

    def test_unchecked_access_blocks_the_whole_workspace(self):
        from app.core.session_context import accessible_workspaces, session_permission_names

        u = _user(roles=["GESTOR"], removes=(WORKSPACE_INDICATORS_ACCESS,))
        self.assertNotIn("indicators", accessible_workspaces(u))
        for code in (pc.INDICATORS_READ, pc.INDICATORS_DIRECTOR, pc.COMPANY_RESULT_READ, pc.COMPANY_RESULT_SENSITIVE):
            self.assertFalse(user_has_permission(u, code), f"{code} deveria sair com o workspace")
        names = set(session_permission_names(u))
        self.assertFalse({n for n in names if n.startswith(("indicators.", "company_result.", "workspace.indicators"))})
        # Os demais workspaces do GESTOR seguem intactos.
        self.assertTrue(user_has_permission(u, pc.PAYABLES_READ))
        self.assertIn("finance", accessible_workspaces(u))


class ImplicationTests(unittest.TestCase):
    def test_verb_chain_employees(self):
        e = expand_permissions({pc.EMPLOYEES_UPDATE})
        for c in (pc.EMPLOYEES_READ, pc.EMPLOYEES_LIST, pc.EMPLOYEES_REFERENCE):
            self.assertIn(c, e)
        self.assertNotIn(pc.EMPLOYEES_SENSITIVE, e)  # update não vaza sensível

    def test_create_does_not_imply_list(self):
        e = expand_permissions({pc.EMPLOYEES_CREATE})
        self.assertIn(pc.EMPLOYEES_REFERENCE, e)
        self.assertNotIn(pc.EMPLOYEES_LIST, e)  # criar não implica listar os demais

    def test_legacy_view_bundle(self):
        e = expand_permissions({pc.EMPLOYEES_VIEW})
        for c in (pc.EMPLOYEES_READ, pc.EMPLOYEES_LIST, pc.EMPLOYEES_REFERENCE, pc.EMPLOYEES_SENSITIVE):
            self.assertIn(c, e)

    def test_legacy_edit_bundle(self):
        e = expand_permissions({pc.EMPLOYEES_EDIT})
        for c in (pc.EMPLOYEES_CREATE, pc.EMPLOYEES_UPDATE, pc.EMPLOYEES_DELETE, pc.EMPLOYEES_SENSITIVE):
            self.assertIn(c, e)

    def test_vehicles_verb_chain_and_legacy(self):
        e = expand_permissions({pc.VEHICLES_UPDATE})
        for c in (pc.VEHICLES_READ, pc.VEHICLES_LIST, pc.VEHICLES_REFERENCE):
            self.assertIn(c, e)
        self.assertNotIn(pc.VEHICLES_SENSITIVE, e)  # update não vaza sensível
        # Legado vehicles.view = leitura + sensível; vehicles.edit = CRUD + sensível.
        v = expand_permissions({pc.VEHICLES_VIEW})
        for c in (pc.VEHICLES_READ, pc.VEHICLES_LIST, pc.VEHICLES_REFERENCE, pc.VEHICLES_SENSITIVE):
            self.assertIn(c, v)
        ed = expand_permissions({pc.VEHICLES_EDIT})
        for c in (pc.VEHICLES_CREATE, pc.VEHICLES_UPDATE, pc.VEHICLES_DELETE, pc.VEHICLES_SENSITIVE):
            self.assertIn(c, ed)

    def test_sensitive_is_orthogonal(self):
        self.assertNotIn(pc.EMPLOYEES_READ, expand_permissions({pc.EMPLOYEES_SENSITIVE}))
        self.assertNotIn(pc.EMPLOYEES_SENSITIVE, expand_permissions({pc.EMPLOYEES_READ}))

    def test_reference_does_not_grant_workspace(self):
        # Usuário só com employees.reference NÃO deve alcançar o workspace de Projetos.
        u = _user(pc.EMPLOYEES_REFERENCE)
        self.assertFalse(user_has_permission(u, WORKSPACE_PROJECTS_ACCESS))

    def test_activation_state(self):
        # Todos os verbos NÃO-sensíveis já ativados (Colaboradores/Ativos/Veículos/Projetos/Financeiro/Leitura),
        # incluindo o novo employees.export (Fase Dados Sensíveis — Colaboradores).
        for c in pc.NEW_PERMISSION_CODES:
            if c.endswith(".sensitive"):
                continue
            self.assertIn(c, ACTIVE_PERMISSION_CODES, f"{c} deveria estar ativo")
        # `*.sensitive` segue INATIVO, EXCETO os módulos cujo eixo Dados Sensíveis já foi ativado
        # (omissão no backend + ocultação no frontend): employees, vehicles, assets, o recurso
        # próprio financial_dashboard (Dashboard Financeiro), o recurso próprio company_result
        # (Resultado da Empresa) e o Jurídico — módulo NOVO, que nasce
        # com o eixo completo (`redact_for("legal_case"/"legal_person"/...)` no router).
        inactive = set(pc.NEW_PERMISSION_CODES) - set(ACTIVE_PERMISSION_CODES)
        expected_inactive = {
            c for c in pc.NEW_PERMISSION_CODES if c.endswith(".sensitive")
        } - {
            pc.EMPLOYEES_SENSITIVE, pc.VEHICLES_SENSITIVE, pc.ASSETS_SENSITIVE,
            pc.FINANCIAL_DASHBOARD_SENSITIVE,
            pc.COMPANY_RESULT_SENSITIVE,
            pc.LEGAL_CASES_SENSITIVE, pc.LEGAL_PERSONS_SENSITIVE,
        }
        self.assertEqual(inactive, expected_inactive)
        for code in (
            pc.EMPLOYEES_SENSITIVE, pc.EMPLOYEES_EXPORT,
            pc.VEHICLES_SENSITIVE, pc.VEHICLES_EXPORT,
            pc.ASSETS_SENSITIVE,
            pc.FINANCIAL_DASHBOARD_READ, pc.FINANCIAL_DASHBOARD_SENSITIVE,
            pc.COMPANY_RESULT_READ, pc.COMPANY_RESULT_SENSITIVE,
            *pc.LEGAL_MODULE_CODES,
        ):
            self.assertIn(code, ACTIVE_PERMISSION_CODES)


class NeutralityGoldenTests(unittest.TestCase):
    """Nenhum código LEGADO pode mudar de resultado por causa da nova infraestrutura."""

    def _users(self) -> list[SimpleNamespace]:
        legacy = _LEGACY_CODES
        users = [
            _user(),  # vazio
            _user(roles=["CONSULTA"]),
            _user(roles=["GESTOR"]),
            _user(roles=["ADMIN"]),
            _user(email=_SUPERUSER_EMAIL),
            _user(pc.EMPLOYEES_VIEW),
            _user(pc.EMPLOYEES_EDIT),  # edit-only (sem view) — caso sensível
            _user(pc.ASSETS_VIEW),
            _user(pc.ASSETS_EDIT),
            _user(pc.PROJECTS_VIEW),
            _user(pc.COMPANY_FINANCE_VIEW),
            _user(pc.COSTS_VIEW, pc.COSTS_EDIT),
            _user(pc.INDICATORS_VIEW),
            _user(*list(PRESET_GESTOR)),
            _user(*list(PRESET_CONSULTA)),
        ]
        # cada código legado isolado
        users += [_user(c) for c in legacy]
        return users

    def test_legacy_codes_unchanged(self):
        legacy_codes = list(_LEGACY_CODES) + [
            WORKSPACE_PROJECTS_ACCESS,
            WORKSPACE_FINANCE_ACCESS,
            WORKSPACE_ASSETS_ACCESS,
            WORKSPACE_INDICATORS_ACCESS,
        ]
        diffs = []
        for u in self._users():
            for code in legacy_codes:
                old = _legacy_has(u, code)
                new = user_has_permission(u, code)
                if old != new:
                    diffs.append((u.email, [p.permission.name for p in u.user_permissions], code, old, new))
        self.assertEqual(diffs, [], f"Divergências de neutralidade: {diffs[:10]}")


class Phase1ProfileIndependenceTests(unittest.TestCase):
    """Fase 1: autorização depende SÓ das permissões — nunca de perfil, e-mail ou system.admin-blanket."""

    def test_system_admin_does_not_unlock_business(self):
        u = _user(SYSTEM_ADMIN)
        for code in (pc.EMPLOYEES_CREATE, pc.EMPLOYEES_VIEW, pc.PAYABLES_EDIT, pc.VEHICLES_CREATE, pc.ASSETS_VIEW):
            self.assertFalse(user_has_permission(u, code), f"system.admin NÃO pode liberar {code}")

    def test_system_admin_grants_only_system_features(self):
        u = _user(SYSTEM_ADMIN)
        for code in (pc.USERS_MANAGE, pc.SETTINGS_VIEW, pc.SETTINGS_EDIT):
            self.assertTrue(user_has_permission(u, code), f"system.admin deve conceder {code}")

    def test_role_name_alone_grants_nothing(self):
        # Perfil chamado "ADMIN" mas SEM permissões não concede nada (role.name é irrelevante).
        u = SimpleNamespace(
            email="x@example.com", user_permissions=[],
            roles=[SimpleNamespace(role=SimpleNamespace(name="ADMIN", permissions=[]))], is_active=True,
        )
        self.assertFalse(user_has_permission(u, pc.EMPLOYEES_VIEW))
        self.assertFalse(user_has_permission(u, pc.USERS_MANAGE))

    def test_no_superuser_email_bypass(self):
        u = _user(email=_SUPERUSER_EMAIL)  # e-mail que era superusuário, mas SEM permissões
        self.assertFalse(user_has_permission(u, pc.EMPLOYEES_VIEW))
        self.assertFalse(user_has_permission(u, pc.USERS_MANAGE))

    def test_full_permissions_gives_full_access(self):
        # "Superusuário" = quem tem TODAS as permissões (mecanismo normal), sem atalho mágico.
        u = _user(*list(pc.ALL_PERMISSION_CODES))
        for code in (pc.EMPLOYEES_CREATE, pc.PAYABLES_EDIT, pc.USERS_MANAGE, pc.VEHICLES_DELETE, pc.SYSTEM_ADMIN):
            self.assertTrue(user_has_permission(u, code))


if __name__ == "__main__":
    unittest.main()
