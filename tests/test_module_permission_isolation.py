"""Isolamento de permissões por módulo.

Cada menu/módulo deve depender EXCLUSIVAMENTE das suas próprias permissões (view/edit), sem herdar
nem exigir permissões de outro módulo. Estes testes exercitam as funções REAIS de autorização
(as mesmas usadas pelos endpoints) com usuários construídos em memória.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from fastapi import HTTPException

from app.api.deps import user_has_permission
from app.core.permission_codes import (
    ASSETS_VIEW,
    COMPANY_FINANCE_EDIT,
    COMPANY_FINANCE_VIEW,
    COSTS_EDIT,
    DEBTS_EDIT,
    DEBTS_VIEW,
    PAYABLES_EDIT,
    PAYABLES_VIEW,
    RECEIVABLES_EDIT,
)
from app.modules.company_finance.router import _assert_edit, _assert_view
from app.modules.reports.router import _assert_report_type_access


def _user(*perms: str) -> SimpleNamespace:
    """Usuário com permissões CUSTOMIZADas (user_permissions) — sem fallback de preset de role.

    email fora da lista de superusuários e sem role ADMIN, para exercitar apenas o RBAC por código.
    """
    ups = [SimpleNamespace(permission=SimpleNamespace(name=p)) for p in perms]
    return SimpleNamespace(
        email="perm-isolation-test@example.com",
        user_permissions=ups,
        roles=[],
        is_superuser=False,
    )


class ModulePermissionIsolationTests(unittest.TestCase):
    # --- Endividamento x Custos Fixos (mesmo endpoint, tipos diferentes) -------------------
    def test_endividamento_view_does_not_grant_custos_fixos(self) -> None:
        user = _user(DEBTS_VIEW)
        _assert_view(user, "endividamento")  # não levanta
        with self.assertRaises(HTTPException) as ctx:
            _assert_view(user, "custo_fixo")  # não tem company_finance.view
        self.assertEqual(ctx.exception.status_code, 403)

    def test_custos_fixos_view_does_not_grant_endividamento(self) -> None:
        user = _user(COMPANY_FINANCE_VIEW)
        _assert_view(user, "custo_fixo")  # não levanta
        with self.assertRaises(HTTPException):
            _assert_view(user, "endividamento")  # não tem debts.view

    def test_endividamento_uses_only_debts_permissions(self) -> None:
        user = _user(DEBTS_VIEW, DEBTS_EDIT)
        _assert_view(user, "endividamento")
        _assert_edit(user, "endividamento")
        # Não deve, por isso, poder editar/visualizar Custos Fixos.
        with self.assertRaises(HTTPException):
            _assert_edit(user, "custo_fixo")

    # --- Ativos x Company Finance ---------------------------------------------------------
    def test_assets_without_company_finance(self) -> None:
        user = _user(ASSETS_VIEW)
        self.assertTrue(user_has_permission(user, ASSETS_VIEW))
        self.assertFalse(user_has_permission(user, COMPANY_FINANCE_VIEW))

    def test_company_finance_without_assets(self) -> None:
        user = _user(COMPANY_FINANCE_VIEW)
        self.assertTrue(user_has_permission(user, COMPANY_FINANCE_VIEW))
        self.assertFalse(user_has_permission(user, ASSETS_VIEW))

    # --- Sem VIEW não acessa; VIEW sem EDIT consulta mas não altera -----------------------
    def test_without_view_has_no_access(self) -> None:
        user = _user(ASSETS_VIEW)  # conjunto não-vazio, mas sem as permissões de finanças
        self.assertFalse(user_has_permission(user, DEBTS_VIEW))
        self.assertFalse(user_has_permission(user, COMPANY_FINANCE_VIEW))
        self.assertFalse(user_has_permission(user, PAYABLES_VIEW))

    def test_view_without_edit_can_read_not_write(self) -> None:
        user = _user(DEBTS_VIEW)  # só leitura de Endividamento
        _assert_view(user, "endividamento")  # consulta OK
        with self.assertRaises(HTTPException):
            _assert_edit(user, "endividamento")  # não pode alterar

    # --- CAP desacoplado de Custos --------------------------------------------------------
    def test_cap_edit_requires_payables_edit_not_costs_edit(self) -> None:
        # Modelo de permissões: costs.edit NÃO concede mais a edição do CAP.
        only_costs = _user(PAYABLES_VIEW, COSTS_EDIT)
        self.assertFalse(user_has_permission(only_costs, PAYABLES_EDIT))
        # Com a permissão própria, edita.
        cap_editor = _user(PAYABLES_VIEW, PAYABLES_EDIT)
        self.assertTrue(user_has_permission(cap_editor, PAYABLES_EDIT))

    def test_receivables_edit_is_own_permission(self) -> None:
        user = _user(RECEIVABLES_EDIT)
        self.assertTrue(user_has_permission(user, RECEIVABLES_EDIT))

    # --- Relatórios exigem a permissão do módulo do relatório -----------------------------
    def test_report_requires_module_permission(self) -> None:
        from app.core.permission_codes import REPORTS_VIEW, ASSETS_VIEW as _AV

        only_reports = _user(REPORTS_VIEW)
        with self.assertRaises(HTTPException):
            _assert_report_type_access(only_reports, "assets_inventory")  # falta assets.view
        with self.assertRaises(HTTPException):
            _assert_report_type_access(only_reports, "debt")  # falta debts.view

        with_module = _user(REPORTS_VIEW, _AV)
        _assert_report_type_access(with_module, "assets_inventory")  # OK

    def test_report_without_reports_permission_denied(self) -> None:
        user = _user(ASSETS_VIEW)  # tem o módulo, mas não reports.view/export
        with self.assertRaises(HTTPException):
            _assert_report_type_access(user, "assets_inventory")


if __name__ == "__main__":
    unittest.main()
