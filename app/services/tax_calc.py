"""Tributos por regime (Lucro Presumido × Lucro Real) — regra pura, sem banco.

O regime vale por competência: o período cadastrado com a maior data de início até o mês
(`tax_regime_periods`). Mês sem período cadastrado usa o percentual de reserva `tax_rate`.

Lucro Presumido (serviços) — tudo sobre a receita, nos dois dashboards:
    PIS 0,65% · COFINS 3% · ISS
    IRPJ = receita × presunção (32%) × 15%  + adicional de 10% sobre a base presumida da EMPRESA
           que passar do limite mensal (R$ 20 mil), repartido entre os projetos pela receita
    CSLL = receita × presunção (32%) × 9%

Lucro Real:
    Sobre a receita (dois dashboards): PIS 1,65% · COFINS 7,6% (menos os créditos estimados) · ISS
    Sobre o LUCRO da empresa (só no Resultado da Empresa): IRPJ 15% + adicional 10% acima do limite
    mensal · CSLL 9% — zero quando há prejuízo.

As retenções de 6,15% na NF (IR, CSLL, PIS, COFINS) são ANTECIPAÇÃO desses mesmos tributos, não um
custo a mais: o custo é o tributo devido, pago na fonte ou em guia.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from app.utils.date_utils import normalize_competencia

LUCRO_PRESUMIDO = "LUCRO_PRESUMIDO"
LUCRO_REAL = "LUCRO_REAL"

_DEFAULTS = {
    "iss_rate": 0.05,
    "pis_presumido_rate": 0.0065,
    "cofins_presumido_rate": 0.03,
    "irpj_presumption_rate": 0.32,
    "csll_presumption_rate": 0.32,
    "irpj_rate": 0.15,
    "irpj_additional_rate": 0.10,
    "irpj_additional_monthly_threshold": 20_000.0,
    "csll_rate": 0.09,
    "pis_real_rate": 0.0165,
    "cofins_real_rate": 0.076,
    "pis_cofins_credit_rate": 0.0,
    "tax_rate": 0.0,
}


@dataclass(frozen=True)
class RevenueTaxes:
    regime: str | None  # None = sem regime cadastrado (percentual de reserva)
    pis: float = 0.0
    cofins: float = 0.0
    iss: float = 0.0
    irpj: float = 0.0
    csll: float = 0.0
    other: float = 0.0  # percentual de reserva quando não há regime

    @property
    def total(self) -> float:
        return self.pis + self.cofins + self.iss + self.irpj + self.csll + self.other


def _p(settings, name: str) -> float:
    value = getattr(settings, name, None)
    return float(_DEFAULTS[name] if value is None else value)


def regime_for_competencia(periods: Iterable[tuple[date, str]], competencia: date) -> str | None:
    """Regime do período com a maior data de início cujo mês é ≤ competência."""
    comp = normalize_competencia(competencia)
    chosen: tuple[date, str] | None = None
    for start, regime in periods:
        start_month = normalize_competencia(start)
        if start_month <= comp and (chosen is None or start_month >= chosen[0]):
            chosen = (start_month, regime)
    return chosen[1] if chosen else None


def revenue_taxes(*, regime: str | None, settings, revenue: float, company_revenue: float) -> RevenueTaxes:
    """Tributos sobre a receita de um projeto (ou da empresa, quando revenue == company_revenue)."""
    revenue = float(revenue or 0)
    if revenue <= 0:
        return RevenueTaxes(regime)
    if regime is None:
        return RevenueTaxes(None, other=revenue * _p(settings, "tax_rate"))
    iss = revenue * _p(settings, "iss_rate")
    if regime == LUCRO_PRESUMIDO:
        company = max(float(company_revenue or 0), revenue)
        presumption_irpj = _p(settings, "irpj_presumption_rate")
        irpj = revenue * presumption_irpj * _p(settings, "irpj_rate")
        company_additional = max(
            company * presumption_irpj - _p(settings, "irpj_additional_monthly_threshold"), 0.0
        ) * _p(settings, "irpj_additional_rate")
        irpj += company_additional * (revenue / company)
        csll = revenue * _p(settings, "csll_presumption_rate") * _p(settings, "csll_rate")
        return RevenueTaxes(
            regime,
            pis=revenue * _p(settings, "pis_presumido_rate"),
            cofins=revenue * _p(settings, "cofins_presumido_rate"),
            iss=iss,
            irpj=irpj,
            csll=csll,
        )
    # Lucro Real: PIS/COFINS não cumulativos, com créditos estimados repartidos na proporção das alíquotas.
    pis_rate = _p(settings, "pis_real_rate")
    cofins_rate = _p(settings, "cofins_real_rate")
    credit = revenue * _p(settings, "pis_cofins_credit_rate")
    gross = pis_rate + cofins_rate
    pis = max(revenue * pis_rate - (credit * pis_rate / gross if gross else 0.0), 0.0)
    cofins = max(revenue * cofins_rate - (credit * cofins_rate / gross if gross else 0.0), 0.0)
    return RevenueTaxes(regime, pis=pis, cofins=cofins, iss=iss)


def profit_taxes_real(*, settings, taxable_profit: float) -> tuple[float, float]:
    """(IRPJ, CSLL) do Lucro Real sobre o lucro mensal da empresa; zero no prejuízo."""
    profit = float(taxable_profit or 0)
    if profit <= 0:
        return 0.0, 0.0
    irpj = profit * _p(settings, "irpj_rate") + max(
        profit - _p(settings, "irpj_additional_monthly_threshold"), 0.0
    ) * _p(settings, "irpj_additional_rate")
    return irpj, profit * _p(settings, "csll_rate")
