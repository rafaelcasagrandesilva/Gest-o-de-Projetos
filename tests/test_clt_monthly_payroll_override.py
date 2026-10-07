"""Cenários 1 e 2: folha real mensal vs comportamento legado em Contas a Pagar CLT."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.services.employee_cost_service import (
    CLT_PAYABLE_LABEL_BENEFIT,
    CLT_PAYABLE_LABEL_SALARY,
    CLT_PAYABLE_LABEL_TERMINATION,
    CLT_PAYABLE_LABEL_TRANSPORT,
    CLT_PAYABLE_LABEL_VACATION,
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
    override = SimpleNamespace(
        net_salary_amount=4137.40, vr_amount=672.00, vacation_advance_amount=None
    )
    lines = clt_payable_components_from_monthly_override(override)
    assert lines == [(CLT_PAYABLE_LABEL_SALARY, 4137.40), (CLT_PAYABLE_LABEL_BENEFIT, 672.00)]

    components = project_labor_payable_snapshot_components(
        _Emp(), None, date(2026, 5, 1), None, payroll_override=override
    )
    assert components == lines


def test_scenario_3_vacation_advance_adds_independent_component():
    """Férias preenchida gera 3ª linha independente 'Férias CLT' (não somada ao salário)."""
    override = SimpleNamespace(
        net_salary_amount=4137.40, vr_amount=672.00, vacation_advance_amount=2500.00
    )
    lines = clt_payable_components_from_monthly_override(override)
    assert lines == [
        (CLT_PAYABLE_LABEL_SALARY, 4137.40),
        (CLT_PAYABLE_LABEL_BENEFIT, 672.00),
        (CLT_PAYABLE_LABEL_VACATION, 2500.00),
    ]

    components = project_labor_payable_snapshot_components(
        _Emp(), None, date(2026, 5, 1), None, payroll_override=override
    )
    assert components == lines


def test_vacation_only_generates_single_component():
    override = SimpleNamespace(
        net_salary_amount=None, vr_amount=None, vacation_advance_amount=1800.00
    )
    lines = clt_payable_components_from_monthly_override(override)
    assert lines == [(CLT_PAYABLE_LABEL_VACATION, 1800.00)]


def test_empty_vacation_generates_no_vacation_component():
    """Campo de férias vazio (None ou 0) → nenhum lançamento de férias."""
    for value in (None, 0, 0.0):
        override = SimpleNamespace(
            net_salary_amount=4137.40, vr_amount=None, vacation_advance_amount=value
        )
        lines = clt_payable_components_from_monthly_override(override)
        assert lines == [(CLT_PAYABLE_LABEL_SALARY, 4137.40)]


def test_missing_vacation_attr_is_backward_compatible():
    """Override legado sem o atributo de férias não quebra (getattr → None)."""
    override = SimpleNamespace(net_salary_amount=5000.0, vr_amount=None)
    lines = clt_payable_components_from_monthly_override(override)
    assert lines == [(CLT_PAYABLE_LABEL_SALARY, 5000.0)]


def test_vt_adds_independent_component_after_vr():
    """VT preenchido gera linha independente "Vale Transporte CLT" (não somada ao VR)."""
    override = SimpleNamespace(
        net_salary_amount=4137.40, vr_amount=672.00, vt_amount=220.00,
        vacation_advance_amount=None,
    )
    lines = clt_payable_components_from_monthly_override(override)
    assert lines == [
        (CLT_PAYABLE_LABEL_SALARY, 4137.40),
        (CLT_PAYABLE_LABEL_BENEFIT, 672.00),
        (CLT_PAYABLE_LABEL_TRANSPORT, 220.00),
    ]

    components = project_labor_payable_snapshot_components(
        _Emp(), None, date(2026, 5, 1), None, payroll_override=override
    )
    assert components == lines


def test_vt_only_generates_single_component():
    override = SimpleNamespace(
        net_salary_amount=None, vr_amount=None, vt_amount=180.00,
        vacation_advance_amount=None,
    )
    lines = clt_payable_components_from_monthly_override(override)
    assert lines == [(CLT_PAYABLE_LABEL_TRANSPORT, 180.00)]


def test_empty_vt_generates_no_transport_component():
    """Campo de VT vazio (None ou 0) → nenhum lançamento de vale transporte."""
    for value in (None, 0, 0.0):
        override = SimpleNamespace(
            net_salary_amount=4137.40, vr_amount=None, vt_amount=value,
            vacation_advance_amount=None,
        )
        lines = clt_payable_components_from_monthly_override(override)
        assert lines == [(CLT_PAYABLE_LABEL_SALARY, 4137.40)]


def test_missing_vt_attr_is_backward_compatible():
    """Override legado sem o atributo de VT não quebra (getattr → None)."""
    override = SimpleNamespace(net_salary_amount=5000.0, vr_amount=672.00)
    lines = clt_payable_components_from_monthly_override(override)
    assert lines == [
        (CLT_PAYABLE_LABEL_SALARY, 5000.0),
        (CLT_PAYABLE_LABEL_BENEFIT, 672.00),
    ]


def test_termination_without_values_generates_no_salary_not_even_from_cadastro():
    # Rescisão: o mês não pode cair no fallback do salário do cadastro.
    override = SimpleNamespace(
        net_salary_amount=None, vr_amount=None, vt_amount=None,
        vacation_advance_amount=None, is_termination=True,
    )
    assert clt_payable_components_from_monthly_override(override) == []
    assert project_labor_payable_snapshot_components(
        _Emp(), None, date(2026, 9, 1), None, payroll_override=override
    ) == []


def test_termination_drops_salary_but_keeps_other_components():
    override = SimpleNamespace(
        net_salary_amount=4137.40, vr_amount=672.00, vt_amount=None,
        vacation_advance_amount=None, is_termination=True,
    )
    assert clt_payable_components_from_monthly_override(override) == [
        (CLT_PAYABLE_LABEL_BENEFIT, 672.00)
    ]


def test_termination_amount_generates_own_component_instead_of_salary():
    override = SimpleNamespace(
        net_salary_amount=2149.27, vr_amount=None, vt_amount=None,
        vacation_advance_amount=None, is_termination=True, termination_amount=2149.27,
    )
    assert clt_payable_components_from_monthly_override(override) == [
        (CLT_PAYABLE_LABEL_TERMINATION, 2149.27)
    ]


def test_termination_amount_ignored_when_flag_is_off():
    override = SimpleNamespace(
        net_salary_amount=4137.40, vr_amount=None, vt_amount=None,
        vacation_advance_amount=None, is_termination=False, termination_amount=999.0,
    )
    assert clt_payable_components_from_monthly_override(override) == [
        (CLT_PAYABLE_LABEL_SALARY, 4137.40)
    ]
