"""Cronograma Financeiro — núcleo genérico e reutilizável (domain-agnostic).

Conceito de PRIMEIRA CLASSE: uma agenda de obrigações (parcela = data + valor + descrição) que é a
FONTE ÚNICA do planejamento de qualquer obrigação com calendário financeiro — endividamento
renegociado hoje; acordos judiciais, parcelamentos tributários, financiamentos e contratos amanhã.

Este módulo NÃO conhece ORM, banco, nem o domínio de Endividamento. Ele opera sobre estruturas
puras (`ScheduleLine`, `RangeSpec`) e concentra:

- o **gerador de faixas** (`expand_range` / `build_schedule`): monta um cronograma grande a partir
  de poucas faixas {parcela inicial, final, valor, dia, 1º vencimento};
- a **validação de fechamento** (`validate_closure`): Σ cronograma vs. valor negociado;
- o **cálculo ÚNICO dos indicadores** (`compute_indicators`): saldo, progresso, valor pago,
  parcelas restantes, próxima/última parcela, data de encerramento — derivados EXCLUSIVAMENTE de
  `linhas planejadas + pagamentos reais por linha`. As linhas são obrigações PLANEJADAS; o valor
  pago vem SEMPRE dos pagamentos reais (no Endividamento, do Contas a Pagar via `entry_id`), nunca
  da soma das linhas.

O adaptador de cada domínio (ex.: Endividamento) é o único responsável por mapear seus registros
para/desta camada. Assim "cronograma financeiro" é reutilizável sem duplicação de regra.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")


def _money(value: object) -> Decimal:
    """Normaliza para Decimal com 2 casas (arredondamento financeiro)."""
    if isinstance(value, Decimal):
        d = value
    else:
        d = Decimal(str(value))
    return d.quantize(CENTS, rounding=ROUND_HALF_UP)


def _clamp_day(year: int, month: int, day: int) -> date:
    """Data (year, month, day) com o dia limitado ao último dia do mês (ex.: 31/02 → 28/02)."""
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last))


def _add_months(base: date, n: int) -> date:
    """base + n meses, preservando o dia (limitado ao último dia do mês de destino)."""
    total = (base.year * 12 + (base.month - 1)) + n
    year, month = divmod(total, 12)
    return _clamp_day(year, month + 1, base.day)


@dataclass(frozen=True)
class ScheduleLine:
    """Uma parcela do cronograma (obrigação PLANEJADA)."""

    seq: int
    due_date: date
    amount: Decimal
    description: str | None = None


@dataclass(frozen=True)
class RangeSpec:
    """Faixa de geração: parcelas [seq_start..seq_end] com o mesmo valor.

    `day` é o dia de vencimento canônico (limitado ao fim do mês). `first_due_month` é o mês da
    PRIMEIRA parcela da faixa (o dia efetivo vem de `day`). Ex.: parcelas 1..6, R$ 15.000, dia 20,
    a partir de 08/2026 → 20/08, 20/09, … 20/01/2027.
    """

    seq_start: int
    seq_end: int
    amount: Decimal
    day: int
    first_due_month: date

    @property
    def count(self) -> int:
        return self.seq_end - self.seq_start + 1


def expand_range(spec: RangeSpec, *, description: str | None = None) -> list[ScheduleLine]:
    """Expande uma faixa em suas parcelas individuais (gerador de faixas).

    `description` opcional é aplicada a todas; quando None usa "Parcela {seq}".
    """
    if spec.seq_start < 1 or spec.seq_end < spec.seq_start:
        raise ValueError("Faixa inválida: exige 1 <= seq_start <= seq_end.")
    if not (1 <= spec.day <= 31):
        raise ValueError("Dia de vencimento inválido (1..31).")
    amount = _money(spec.amount)
    if amount <= 0:
        raise ValueError("Valor da parcela deve ser maior que zero.")

    base_year, base_month = spec.first_due_month.year, spec.first_due_month.month
    lines: list[ScheduleLine] = []
    for offset, seq in enumerate(range(spec.seq_start, spec.seq_end + 1)):
        anchor = _add_months(date(base_year, base_month, 1), offset)
        due = _clamp_day(anchor.year, anchor.month, spec.day)
        lines.append(
            ScheduleLine(
                seq=seq,
                due_date=due,
                amount=amount,
                description=description or f"Parcela {seq}",
            )
        )
    return lines


def build_schedule(specs: list[RangeSpec]) -> list[ScheduleLine]:
    """Concatena faixas em um cronograma completo, validando sequência contígua e sem sobreposição.

    Exige que as faixas cubram 1..N sem lacunas nem repetição de `seq` (ordem de entrada livre).
    """
    if not specs:
        return []
    ordered = sorted(specs, key=lambda s: s.seq_start)
    lines: list[ScheduleLine] = []
    expected = ordered[0].seq_start
    if expected != 1:
        raise ValueError("O cronograma deve começar na parcela 1.")
    for spec in ordered:
        if spec.seq_start != expected:
            raise ValueError(
                f"Faixas com lacuna/sobreposição: esperado seq {expected}, recebido {spec.seq_start}."
            )
        lines.extend(expand_range(spec))
        expected = spec.seq_end + 1
    return lines


def schedule_total(lines: list[ScheduleLine]) -> Decimal:
    return _money(sum((ln.amount for ln in lines), Decimal("0")))


@dataclass(frozen=True)
class ClosureResult:
    """Resultado da validação de fechamento do cronograma vs. valor negociado."""

    total_negociado: Decimal
    total_cronograma: Decimal
    diferenca: Decimal  # negociado - cronograma (0 = fecha)
    is_valid: bool


def validate_closure(
    total_negociado: object,
    lines: list[ScheduleLine],
    *,
    tolerance: Decimal = Decimal("0.00"),
) -> ClosureResult:
    """Valida se Σ cronograma fecha o valor negociado (dentro de uma tolerância opcional)."""
    negociado = _money(total_negociado)
    total = schedule_total(lines)
    diff = _money(negociado - total)
    return ClosureResult(
        total_negociado=negociado,
        total_cronograma=total,
        diferenca=diff,
        is_valid=abs(diff) <= _money(tolerance),
    )


@dataclass(frozen=True)
class ScheduleIndicators:
    """Indicadores da obrigação, derivados de linhas planejadas + pagamentos reais por linha.

    FONTE ÚNICA: `paid_by_seq` traz o valor REALMENTE pago de cada parcela (no Endividamento, o
    `amount_paid` do título do CAP vinculado por `entry_id`). Nunca se soma o cronograma como pago.
    """

    total_negociado: Decimal
    total_cronograma: Decimal
    total_pago: Decimal
    saldo_restante: Decimal
    progresso: float  # 0..1
    parcelas_total: int
    parcelas_pagas: int
    parcelas_restantes: int
    proxima_parcela: ScheduleLine | None
    ultima_parcela: ScheduleLine | None
    data_encerramento: date | None


def compute_indicators(
    *,
    total_negociado: object,
    lines: list[ScheduleLine],
    paid_by_seq: dict[int, object] | None = None,
) -> ScheduleIndicators:
    """Calcula todos os indicadores da obrigação a partir do cronograma + pagamentos reais.

    - `lines`: parcelas planejadas (fonte do planejamento).
    - `paid_by_seq`: {seq → valor pago real}. Ausência = 0 pago. Uma parcela é considerada PAGA
      quando o pago real ≥ valor planejado da parcela.
    """
    paid_by_seq = paid_by_seq or {}
    negociado = _money(total_negociado)
    total_cronograma = schedule_total(lines)
    total_pago = _money(sum((Decimal(str(paid_by_seq.get(ln.seq, 0))) for ln in lines), Decimal("0")))
    saldo = _money(max(Decimal("0"), negociado - total_pago))
    progresso = float(total_pago / negociado) if negociado > 0 else 0.0
    progresso = max(0.0, min(1.0, progresso))

    ordered = sorted(lines, key=lambda ln: (ln.due_date, ln.seq))
    pagas = [ln for ln in ordered if _money(paid_by_seq.get(ln.seq, 0)) >= ln.amount]
    abertas = [ln for ln in ordered if _money(paid_by_seq.get(ln.seq, 0)) < ln.amount]

    return ScheduleIndicators(
        total_negociado=negociado,
        total_cronograma=total_cronograma,
        total_pago=total_pago,
        saldo_restante=saldo,
        progresso=progresso,
        parcelas_total=len(ordered),
        parcelas_pagas=len(pagas),
        parcelas_restantes=len(abertas),
        proxima_parcela=abertas[0] if abertas else None,
        ultima_parcela=ordered[-1] if ordered else None,
        data_encerramento=ordered[-1].due_date if ordered else None,
    )
