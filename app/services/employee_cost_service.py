from __future__ import annotations

from datetime import date
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


def _labor_num(labor_row: Any | None, attr: str) -> float | None:
    if labor_row is None:
        return None
    v = getattr(labor_row, attr, None)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def labor_row_total_override_value(labor_row: Any | None) -> float | None:
    """Override absoluto de custo integral (1). None se não definido."""
    return _labor_num(labor_row, "cost_total_override")


def labor_row_salary_base_override_value(labor_row: Any | None) -> float | None:
    """Override de salário/base mensal na linha do projeto (2). None se não definido."""
    return _labor_num(labor_row, "cost_salary_base")


def clt_cost_breakdown_with_labor_overrides(
    employee: Any, settings: Any, year: int, month: int, labor_row: Any | None
) -> dict[str, float]:
    ob = labor_row_salary_base_override_value(labor_row)
    salary_base = ob if ob is not None else float(employee.salary_base or 0)
    dias_uteis = get_business_days(year, month)
    vr_value = float(getattr(settings, "vr_value", 0) or 0)
    vr_total = vr_value * max(dias_uteis, 0)

    peric = salary_base * 0.3 if bool(getattr(employee, "has_periculosidade", False)) else 0.0
    dirigida = DIRIGIDA_MONTHLY_AMOUNT if bool(getattr(employee, "has_adicional_dirigida", False)) else 0.0

    valor_hora = salary_base / CLT_MONTHLY_HOURS_REFERENCE if CLT_MONTHLY_HOURS_REFERENCE else 0.0
    h50 = _labor_num(labor_row, "cost_extra_hours_50")
    if h50 is None:
        h50 = float(getattr(employee, "extra_hours_50", 0) or 0)
    h70 = _labor_num(labor_row, "cost_extra_hours_70")
    if h70 is None:
        h70 = float(getattr(employee, "extra_hours_70", 0) or 0)
    h100 = _labor_num(labor_row, "cost_extra_hours_100")
    if h100 is None:
        h100 = float(getattr(employee, "extra_hours_100", 0) or 0)
    extra_50 = valor_hora * 1.5 * h50
    extra_70 = valor_hora * 1.7 * h70
    extra_100 = valor_hora * 2.0 * h100
    horas_extras = extra_50 + extra_70 + extra_100

    payroll = salary_base + peric + dirigida + horas_extras
    rate = float(getattr(settings, "clt_charges_rate", 0) or 0)
    encargos = payroll * rate
    additional = _labor_num(labor_row, "cost_additional_costs")
    if additional is None:
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


def pj_cost_breakdown_with_labor_overrides(employee: Any, labor_row: Any | None) -> dict[str, float]:
    sb_ov = labor_row_salary_base_override_value(labor_row)
    sb = sb_ov if sb_ov is not None else float(employee.salary_base or 0)
    hrs = _labor_num(labor_row, "cost_pj_hours_per_month")
    if hrs is None:
        hrs_attr = getattr(employee, "pj_hours_per_month", None)
        hrs = float(hrs_attr) if hrs_attr is not None else None
    base = sb * float(hrs) if hrs is not None and float(hrs) > 0 else sb
    ajuda = _labor_num(labor_row, "cost_pj_additional_cost")
    if ajuda is None:
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


def project_labor_cost_base_source(employee: Any, labor_row: Any | None) -> str:
    """
    Origem da base de cálculo para UX.
    CADASTRO | OVERRIDE_SALARY | OVERRIDE_TOTAL
    """
    if labor_row is not None and labor_row_total_override_value(labor_row) is not None:
        return "OVERRIDE_TOTAL"
    if labor_row is not None and labor_row_salary_base_override_value(labor_row) is not None:
        return "OVERRIDE_SALARY"
    return "CADASTRO"


def project_labor_monthly_cost_breakdown(
    employee: Any, settings: Any, competencia: date, labor_row: Any | None
) -> dict[str, float]:
    """Custo mensal integral do colaborador antes do rateio % do projeto (com overrides da linha project_labors).

    Prioridade obrigatória:
    1) cost_total_override definido → custo integral = esse valor
    2) cost_salary_base definido → substitui totalmente employee.salary_base no cálculo CLT/PJ
    3) fallback → cadastro do colaborador
    """
    total_ov = labor_row_total_override_value(labor_row)
    if total_ov is not None:
        t = float(total_ov)
        return {
            "salary_base": 0.0,
            "periculosidade": 0.0,
            "adicional_dirigida": 0.0,
            "vr": 0.0,
            "horas_extras": 0.0,
            "encargos": 0.0,
            "additional_costs": 0.0,
            "ajuda_custo": 0.0,
            "total": t,
        }
    if (employee.employment_type or "").strip().upper() == "CLT":
        return clt_cost_breakdown_with_labor_overrides(
            employee, settings, competencia.year, competencia.month, labor_row
        )
    return pj_cost_breakdown_with_labor_overrides(employee, labor_row)


def project_labor_full_monthly_cost(
    employee: Any, settings: Any, competencia: date, labor_row: Any | None
) -> float:
    return float(project_labor_monthly_cost_breakdown(employee, settings, competencia, labor_row)["total"])
