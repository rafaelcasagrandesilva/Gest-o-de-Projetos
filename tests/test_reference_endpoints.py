"""Autorização e formato dos endpoints de REFERÊNCIA dos pickers (Etapas 1/2).

- /collaborators/search  → exige employees.reference (legado employees.view continua passando).
- /cost-centers/reference → exige cost_center.reference (legados que o implicam continuam passando).

Cobre, por endpoint: permitido / negado / e o invariante de sensibilidade (a resposta NUNCA contém
salário, custo, encargos ou qualquer campo financeiro — só os mínimos de seleção).
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.api.deps import user_has_permission
from app.core import permission_codes as pc

_FINANCIAL_KEYS = {
    "salary_base", "additional_costs", "total_cost", "pj_additional_cost", "pix_key",
    "contract_value", "contract_number", "buyer_name", "buyer_email", "manager_email",
    "cost", "salary", "encargos",
}


def _user(*perms: str) -> SimpleNamespace:
    ups = [SimpleNamespace(permission=SimpleNamespace(name=p), granted=True) for p in perms]
    return SimpleNamespace(email="ref-test@example.com", user_permissions=ups, roles=[], is_active=True)


class CrudVerbAuthorizationTests(unittest.TestCase):
    """Fase 2 — Lote A: cada verbo é concedido pelo próprio código, pelo legado equivalente, e
    NEGADO para quem não tem a permissão específica (separação real dos verbos)."""

    # recurso → (código legado view, código legado edit)
    _MODULES = {
        "employees": (pc.EMPLOYEES_VIEW, pc.EMPLOYEES_EDIT),
        "assets": (pc.ASSETS_VIEW, pc.ASSETS_EDIT),
        "vehicles": (pc.VEHICLES_VIEW, pc.VEHICLES_EDIT),
        "projects": (pc.PROJECTS_VIEW, pc.PROJECTS_EDIT),
    }
    # Projetos: create/delete são códigos legados próprios (não vêm de projects.edit).
    _WRITE_VIA_EDIT = {
        "employees": ("create", "update", "delete"),
        "assets": ("create", "update", "delete"),
        "vehicles": ("create", "update", "delete"),
        "projects": ("update",),
    }

    def test_read_verbs_via_own_and_legacy_view(self):
        for r, (legacy_view, _legacy_edit) in self._MODULES.items():
            for verb in ("reference", "list", "read"):
                code = f"{r}.{verb}"
                self.assertTrue(user_has_permission(_user(code), code), f"{code} pelo próprio código")
                self.assertTrue(user_has_permission(_user(legacy_view), code), f"{code} via {legacy_view}")

    def test_write_verbs_via_own_and_legacy_edit(self):
        for r, (_legacy_view, legacy_edit) in self._MODULES.items():
            for verb in self._WRITE_VIA_EDIT[r]:
                code = f"{r}.{verb}"
                self.assertTrue(user_has_permission(_user(code), code), f"{code} pelo próprio código")
                self.assertTrue(user_has_permission(_user(legacy_edit), code), f"{code} via {legacy_edit}")

    def test_read_does_not_grant_write(self):
        # Quem só LÊ não pode criar/editar/excluir (separação read × write).
        for r, (legacy_view, _e) in self._MODULES.items():
            reader = _user(legacy_view)  # legado view ⇒ reference/list/read (+sensitive), nunca write
            for verb in ("create", "update", "delete"):
                self.assertFalse(user_has_permission(reader, f"{r}.{verb}"), f"{r}.{verb} NÃO por {legacy_view}")

    def test_update_does_not_grant_delete_or_create(self):
        for r in self._MODULES:
            u = _user(f"{r}.update")
            self.assertFalse(user_has_permission(u, f"{r}.delete"), f"{r}.update não concede delete")
            self.assertFalse(user_has_permission(u, f"{r}.create"), f"{r}.update não concede create")

    def test_list_does_not_grant_read(self):
        for r in self._MODULES:
            self.assertFalse(user_has_permission(_user(f"{r}.list"), f"{r}.read"), f"{r}.list não concede read")


class ReferenceAuthorizationTests(unittest.TestCase):
    # --- /collaborators/search → employees.reference ---
    def test_search_allowed_with_reference(self):
        self.assertTrue(user_has_permission(_user(pc.EMPLOYEES_REFERENCE), pc.EMPLOYEES_REFERENCE))

    def test_search_allowed_with_legacy_view(self):
        # employees.view (legado) implica employees.reference no grafo → compatibilidade.
        self.assertTrue(user_has_permission(_user(pc.EMPLOYEES_VIEW), pc.EMPLOYEES_REFERENCE))

    def test_search_denied_without_permission(self):
        # Usuário só de Ativos NÃO deve poder referenciar colaboradores sem o grant.
        self.assertFalse(user_has_permission(_user(pc.ASSETS_EDIT), pc.EMPLOYEES_REFERENCE))

    # --- /cost-centers/reference → cost_center.reference ---
    def test_cc_allowed_with_reference(self):
        self.assertTrue(user_has_permission(_user(pc.COST_CENTER_REFERENCE), pc.COST_CENTER_REFERENCE))

    def test_cc_allowed_with_legacy_implications(self):
        # Recursos que têm Centro de Custo (colaborador/ativo/projeto/veículo/finanças) implicam a referência.
        for legacy in (pc.EMPLOYEES_VIEW, pc.ASSETS_VIEW, pc.PROJECTS_VIEW, pc.COMPANY_FINANCE_VIEW, pc.VEHICLES_VIEW):
            self.assertTrue(
                user_has_permission(_user(legacy), pc.COST_CENTER_REFERENCE),
                f"{legacy} deveria implicar cost_center.reference",
            )

    def test_cc_denied_without_permission(self):
        # Código sem relação com centro de custo NÃO deve concedê-lo.
        self.assertFalse(user_has_permission(_user(pc.DASHBOARD_VIEW), pc.COST_CENTER_REFERENCE))

    # --- POST /employees (criar colaborador) → employees.create ---
    def test_create_allowed_with_create(self):
        self.assertTrue(user_has_permission(_user(pc.EMPLOYEES_CREATE), pc.EMPLOYEES_CREATE))

    def test_create_allowed_with_legacy_edit(self):
        # employees.edit (legado) implica employees.create no grafo → compatibilidade.
        self.assertTrue(user_has_permission(_user(pc.EMPLOYEES_EDIT), pc.EMPLOYEES_CREATE))

    def test_create_denied_with_only_view_or_read(self):
        # Ver/listar NÃO permite criar (separação read × create).
        self.assertFalse(user_has_permission(_user(pc.EMPLOYEES_VIEW), pc.EMPLOYEES_CREATE))
        self.assertFalse(user_has_permission(_user(pc.EMPLOYEES_READ, pc.EMPLOYEES_LIST), pc.EMPLOYEES_CREATE))

    # --- POST /vehicles (criar veículo) → vehicles.create ---
    def test_vehicle_create_allowed_with_create(self):
        self.assertTrue(user_has_permission(_user(pc.VEHICLES_CREATE), pc.VEHICLES_CREATE))

    def test_vehicle_create_allowed_with_legacy_edit(self):
        # vehicles.edit (legado) implica vehicles.create → compatibilidade (ponto 3).
        self.assertTrue(user_has_permission(_user(pc.VEHICLES_EDIT), pc.VEHICLES_CREATE))

    def test_vehicle_create_denied_with_only_view_or_read(self):
        self.assertFalse(user_has_permission(_user(pc.VEHICLES_VIEW), pc.VEHICLES_CREATE))
        self.assertFalse(user_has_permission(_user(pc.VEHICLES_READ, pc.VEHICLES_LIST), pc.VEHICLES_CREATE))


class ReferenceResponseShapeDBTests(unittest.IsolatedAsyncioTestCase):
    """A resposta dos endpoints de referência NUNCA traz dado financeiro (invariante sem/com sensitive)."""

    async def test_collaborator_search_returns_only_id_name(self):
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError
        from app.database.session import AsyncSessionLocal, engine
        from app.modules.collaborators.router import search_collaborators

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            try:
                await s.execute(text("SELECT 1 FROM employees LIMIT 1"))
            except ProgrammingError:
                self.skipTest("Tabela employees ausente.")
            rows = await search_collaborators(db=s, q="a", project_id=None, limit=5)
            for r in rows:
                self.assertEqual(set(r.keys()), {"id", "name"}, f"item de referência com campos extras: {r}")

    async def test_cost_center_reference_returns_only_ref_label(self):
        from app.database.session import AsyncSessionLocal, engine
        from app.modules.cost_centers.router import list_cost_center_references

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            rows = await list_cost_center_references(db=s)
            for r in rows:
                keys = set(r.model_dump().keys())
                self.assertEqual(keys, {"ref", "label"})
                self.assertFalse(keys & _FINANCIAL_KEYS)


if __name__ == "__main__":
    unittest.main()
