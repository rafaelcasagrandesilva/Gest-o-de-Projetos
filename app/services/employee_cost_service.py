from __future__ import annotations

from typing import Any

from app.utils.date_utils import get_business_days

DIRIGIDA_MONTHLY_AMOUNT = 209.24
CLT_MONTHLY_HOURS_REFERENCE = 220


def clt_cost_breakdown(employee: Any, settings: Any, year: int, month: int) -> dict[str, float]:
    salary_base = float(employee.salary_base or 0)
    dias_uteis = get_business_days(year, month)
    vr_value = float(getattr(settings, "vr_value", 0) or 0)
    vr_total = vr_value * max(dias_uteis, 0)

    peric = salary_base * 0.3 if bool(getattr(employee, "has_periculosidade", False)) else 0.0
    dirigida = DIRIGIDA_MONTHLY_AMOUNT if bool(getattr(employee, "has_adicional_dirigida", False)) else 0.0

    valor_hora = salary_base / CLT_MONTHLY_HOURS_REFERENCE if CLT_MONTHLY_HOURS_REFERENCE else 0.0
    h50 = float(getattr(employee, "extra_hours_50", 0) or 0)
    h70 = float(getattr(employee, "extra_hours_70", 0) or 0)
    h100 = float(getattr(employee, "extra_hours_100", 0) or 0)
    extra_50 = valor_hora * 1.5 * h50
    extra_70 = valor_hora * 1.7 * h70
    extra_100 = valor_hora * 2.0 * h100
    horas_extras = extra_50 + extra_70 + extra_100

    payroll = salary_base + peric + dirigida + horas_extras
    rate = float(getattr(settings, "clt_charges_rate", 0) or 0)
    encargos = payroll * rate
    additional = float(getattr(employee, "additional_costs", 0) or 0)
    total = payroll + encargos + vr_total + additional
    return {
        "salary_base": salary_base,
        "periculosidade": peric,
        "adicional_dirigida": dirigida,
        "vr": vr_total,
        "horas_extras": horas_extras,
        "encargos": encargos,
        "additional_costs": additional,
        "ajuda_custo": 0.0,
        "total": float(total),
    }


def pj_cost_breakdown(employee: Any) -> dict[str, float]:
    sb = float(employee.salary_base or 0)
    hrs = getattr(employee, "pj_hours_per_month", None)
    base = sb * float(hrs) if hrs is not None and float(hrs) > 0 else sb
    ajuda = float(getattr(employee, "pj_additional_cost", 0) or 0)
    total = base + ajuda
    return {
        "salary_base": base,
        "periculosidade": 0.0,
        "adicional_dirigida": 0.0,
        "vr": 0.0,
        "horas_extras": 0.0,
        "encargos": 0.0,
        "additional_costs": 0.0,
        "ajuda_custo": ajuda,
        "total": float(total),
    }


def calculate_clt_cost(employee: Any, settings: Any, year: int, month: int) -> float:
    return clt_cost_breakdown(employee, settings, year, month)["total"]


def calculate_pj_total_cost(employee: Any) -> float:
    return pj_cost_breakdown(employee)["total"]


def calculate_clt_cost_fields(
    *,
    salary_base: float,
    has_periculosidade: bool,
    has_adicional_dirigida: bool,
    extra_hours_50: float,
    extra_hours_70: float,
    extra_hours_100: float,
    additional_costs: float,
    vr_value: float,
    clt_charges_rate: float,
    year: int,
    month: int,
) -> float:
    """Usado pelo preview de colaborador CLT (sem ORM employee/settings completos)."""
    class _E:
        pass

    class _S:
        pass

    e = _E()
    e.salary_base = salary_base
    e.has_periculosidade = has_periculosidade
    e.has_adicional_dirigida = has_adicional_dirigida
    e.extra_hours_50 = extra_hours_50
    e.extra_hours_70 = extra_hours_70
    e.extra_hours_100 = extra_hours_100
    e.additional_costs = additional_costs
    s = _S()
    s.vr_value = vr_value
    s.clt_charges_rate = clt_charges_rate
    return clt_cost_breakdown(e, s, year, month)["total"]
