"""Regras PURAS do cadastro corporativo (Custos Indiretos / Endividamento) por competência.

Fonte única de "quanto um item vale no mês" e "o item está vigente no mês". Usadas pela
geração do Contas a Pagar (`PayableSnapshotService`), pela etiqueta de mão de obra dos
colaboradores e pelo painel Resultado da Empresa — sem banco e sem sessão, para que nenhum
desses lugares tenha uma regra paralela.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.models.company_finance import CompanyFinancialItemType
from app.services.employee_cost_service import calculate_clt_cost, calculate_pj_total_cost
from app.utils.date_utils import normalize_competencia

_MONEY_QUANT = Decimal("0.01")


def money2(value: object) -> Decimal:
    """Valor monetário com 2 casas — evita comparações quebradas por float / Numeric impreciso."""
    if value is None:
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)
    return Decimal(str(round(float(value), 2))).quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)


def month_bounds(comp: date) -> tuple[date, date]:
    c = normalize_competencia(comp)
    last = calendar.monthrange(c.year, c.month)[1]
    return date(c.year, c.month, 1), date(c.year, c.month, last)


def reference_monthly_value(item, *, comp: date, settings) -> Decimal:
    """Valor mensal do lançamento automático (congelado no snapshot).

    - Custo indireto colaborador (COLABORADOR_MATRIZ): custo do colaborador no mês × %;
    - Custo indireto comum: valor mensal de referência;
    - Endividamento: parcela prevista (installment_value) ou saldo/valor de referência
      — mesma base já usada pelas pendências, sem alterar cálculo financeiro.
    """
    if item.tipo == "custo_fixo":
        emp = getattr(item, "employee", None)
        pct = getattr(item, "percentual", None)
        if (
            getattr(item, "item_type", None) == CompanyFinancialItemType.COLABORADOR_MATRIZ
            and emp is not None
            and pct is not None
        ):
            if (getattr(emp, "employment_type", "") or "").upper() == "CLT":
                base = calculate_clt_cost(emp, settings, comp.year, comp.month)
            else:
                base = calculate_pj_total_cost(emp)
            return money2(float(base) * (float(pct) / 100.0))
        return money2(item.valor_referencia)
    # Endividamento
    rt = getattr(item, "renegotiation_type", None)
    rt_val = getattr(rt, "value", rt)
    if (
        getattr(item, "has_renegotiation", False)
        and rt_val == "INSTALLMENTS"
        and getattr(item, "installment_value", None) is not None
    ):
        return money2(item.installment_value)
    if getattr(item, "has_renegotiation", False) and getattr(item, "renegotiated_amount", None) is not None:
        return money2(item.renegotiated_amount)
    return money2(item.valor_referencia)


def item_eligible_for_comp(item, comp: date) -> bool:
    """Item elegível a lançamento automático na competência (ciclo de vida + vigência).

    Mesma regra da geração, SEM o piso de implantação: item ativo, vigência cobrindo o
    mês e, para endividamento, "Obrigatório mensal". Usada para materializar a linha
    quando o usuário informa explicitamente o valor da competência na grade (manutenção
    de competência ABERTA anterior ao piso — ex.: DEX em Junho).
    """
    if not bool(getattr(item, "is_active", True)):
        return False
    _, month_end = month_bounds(comp)
    start = getattr(item, "start_date", None)
    end = getattr(item, "end_date", None)
    if start is not None and start > month_end:
        return False
    if end is not None and end < normalize_competencia(comp):
        return False
    # Modo 2 (Cronograma Financeiro Personalizado): elegível pela vigência apenas — cada
    # competência que possui parcela do cronograma gera seu título; "Obrigatório mensal" é
    # conceito do Modo 1 e não se aplica. Legado/Modo 1 permanece exigindo o obrigatório.
    if (
        item.tipo == "endividamento"
        and not bool(getattr(item, "uses_custom_schedule", False))
        and not bool(getattr(item, "is_monthly_required", False))
    ):
        return False
    return True
