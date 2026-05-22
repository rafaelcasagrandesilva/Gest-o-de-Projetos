"""Cenários 1 e 2: folha real mensal vs comportamento legado em Contas a Pagar CLT."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.services.employee_cost_service import (
    CLT_PAYABLE_LABEL_BENEFIT,
    CLT_PAYABLE_LABEL_SALARY,
    clt_payable_components_from_monthly_override,
    project_labor_payable_snapshot_components,
)


class _Emp:
    employment_type = "CLT"
    salary_base = 5000.0


def test_scenario_1_without_override_uses_salary_base():
    emp = _Emp()
    components = project_labor_payable_snapshot_components(
        emp, None, date(2026, 5, 1), None, payroll_override=None
    )
    assert components == [("", 5000.0)]


def test_scenario_2_with_override_splits_salary_and_vr():
    override = SimpleNamespace(net_salary_amount=4137.40, vr_amount=672.00)
    lines = clt_payable_components_from_monthly_override(override)
    assert lines == [(CLT_PAYABLE_LABEL_SALARY, 4137.40), (CLT_PAYABLE_LABEL_BENEFIT, 672.00)]

    components = project_labor_payable_snapshot_components(
        _Emp(), None, date(2026, 5, 1), None, payroll_override=override
    )
    assert components == lines
