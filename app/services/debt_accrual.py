"""Motor de saldo de uma obrigação — núcleo genérico e reutilizável (domain-agnostic).

Conceito de PRIMEIRA CLASSE: um **razão mensal** que transforma uma dívida de "valor parado"
em "saldo que evolui". Serve o Endividamento hoje; parcelamento tributário, financiamento e
acordo judicial amanhã — qualquer obrigação cujo saldo cresça com encargo e diminua com
pagamento.

Este módulo NÃO conhece ORM, banco, nem o domínio de Endividamento. Ele opera sobre estruturas
puras (`RateChange`, `LedgerEvent`, `LedgerLine`) e concentra:

- a **resolução da taxa vigente** (`rate_for`): qual taxa vale em cada competência;
- a **construção do razão** (`build_ledger`): uma linha por mês, no formato da planilha que o
  financeiro já usa (saldo inicial → encargo → pagamento → saldo final);
- o **cálculo ÚNICO dos indicadores** (`compute_indicators`): principal, encargo acumulado,
  quanto do encargo virou caixa e quanto virou saldo, amortização real, saldo atual.

O razão é DERIVADO, nunca armazenado: recalculá-lo a partir de (principal, vigências, eventos,
pagamentos reais) é sempre correto e barato. Sem tabela de saldo não existe saldo defasado, e
corrigir uma taxa lançada errada conserta o histórico inteiro sozinho.

**Pagamento é sempre pagamento REAL** (no Endividamento, o `amount_paid` dos títulos do Contas
a Pagar). O motor nunca soma "valor planejado" como pago — mesma regra do `financial_schedule`.

Regras de cálculo (conferidas contra a planilha real de um acordo com fornecedor, 28
competências, 04/2024–07/2026 — ver tests/test_debt_accrual.py):

    encargo      = saldo_inicial × taxa vigente        (ANTES do aporte do mês entrar)
    saldo_final  = saldo_inicial + aporte + encargo_manual − abatimento − pagamento

1. O aporte não rende encargo no mês em que entra.
2. Encargo não pago é CAPITALIZADO: fica no saldo e rende no mês seguinte.
3. O pagamento quita primeiro o encargo DO MÊS e o excedente amortiza principal. Encargo de
   meses anteriores não fica em aberto: ele já virou saldo (regra 2), e cobrá-lo de novo como
   "juros em aberto" seria contá-lo duas vezes.
4. Taxa 0% congela a dívida — o razão roda e o saldo simplesmente não anda.
5. Saldo não-positivo não rende encargo.
6. Arredondamento a cada mês, 2 casas, ROUND_HALF_UP (mesma convenção do resto do sistema).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")
ZERO = Decimal("0.00")

# Eventos que mexem no saldo sem serem pagamento (pagamento vem do CAP).
APORTE = "APORTE"  # + dívida nova contratada no meio do caminho
ABATIMENTO = "ABATIMENTO"  # − perdão/desconto negociado (não é caixa)
ENCARGO_MANUAL = "ENCARGO_MANUAL"  # + multa, honorário, encargo lançado à mão
EVENT_KINDS = (APORTE, ABATIMENTO, ENCARGO_MANUAL)


def _money(value: object) -> Decimal:
    """Normaliza para Decimal com 2 casas (arredondamento financeiro)."""
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    return d.quantize(CENTS, rounding=ROUND_HALF_UP)


def _rate(value: object) -> Decimal:
    """Normaliza uma taxa mensal (6 casas — 0,5% a.m. = 0.005000)."""
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    return d.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def first_of_month(d: date) -> date:
    return date(d.year, d.month, 1)


def add_months(base: date, n: int) -> date:
    """base + n meses, sempre devolvendo primeiro-de-mês (o razão trabalha por competência)."""
    total = (base.year * 12 + (base.month - 1)) + n
    year, month = divmod(total, 12)
    return date(year, month + 1, 1)


def months_between(a: date, b: date) -> int:
    """Diferença em meses (b − a), ignorando o dia."""
    return (b.year - a.year) * 12 + (b.month - a.month)


@dataclass(frozen=True)
class RateChange:
    """Vigência de taxa: a partir de `valid_from` (competência), vale `monthly_rate`.

    A taxa de um mês é a da MAIOR `valid_from` menor ou igual a ele. Uma dívida que sai de 3%
    para 1,5% a.m. em 01/2026 são duas vigências — nunca uma edição destrutiva da anterior.
    """

    valid_from: date
    monthly_rate: Decimal


@dataclass(frozen=True)
class LedgerEvent:
    """Movimento de saldo que não é pagamento (ver APORTE / ABATIMENTO / ENCARGO_MANUAL)."""

    competencia: date
    kind: str
    amount: Decimal
    description: str | None = None


@dataclass(frozen=True)
class LedgerLine:
    """Uma competência do razão — as mesmas colunas da planilha do financeiro."""

    competencia: date
    saldo_inicial: Decimal
    aporte: Decimal
    abatimento: Decimal
    encargo_manual: Decimal
    taxa: Decimal
    encargo: Decimal
    pagamento: Decimal
    juros_pagos: Decimal
    amortizacao: Decimal
    saldo_final: Decimal
    encargo_acumulado: Decimal
    #: True quando a linha é PROJEÇÃO (competência posterior ao realizado) — a tela pinta
    #: essas linhas em cinza. Quem decide o corte é o chamador, não o núcleo.
    is_projected: bool = False


@dataclass(frozen=True)
class DebtIndicators:
    """Indicadores da dívida, derivados exclusivamente do razão."""

    principal: Decimal
    total_aportes: Decimal
    total_abatimentos: Decimal
    total_encargos: Decimal
    #: Encargo que virou caixa (foi pago) × encargo que virou saldo (capitalizado).
    encargos_pagos: Decimal
    encargos_capitalizados: Decimal
    total_pago: Decimal
    total_amortizado: Decimal
    saldo_atual: Decimal
    taxa_vigente: Decimal
    competencia_final: date | None
    #: Σ (principal + aportes + encargos manuais) — a dívida contratada, sem encargo de taxa.
    total_contratado: Decimal
    #: Saldo no fim da PROJEÇÃO (None quando não há linha projetada). Fica separado de
    #: `saldo_atual` de propósito: um é fato, o outro é hipótese.
    saldo_projetado: Decimal | None = None
    competencia_projecao: date | None = None


def normalize_rates(rates: list[RateChange]) -> list[RateChange]:
    """Ordena as vigências e recusa datas repetidas (ambiguidade de qual taxa vale)."""
    seen: set[date] = set()
    out: list[RateChange] = []
    for r in rates:
        comp = first_of_month(r.valid_from)
        if comp in seen:
            raise ValueError(f"Duas vigências de taxa na mesma competência: {comp:%m/%Y}.")
        seen.add(comp)
        out.append(RateChange(valid_from=comp, monthly_rate=_rate(r.monthly_rate)))
    return sorted(out, key=lambda r: r.valid_from)


def rate_for(competencia: date, rates: list[RateChange]) -> Decimal:
    """Taxa vigente na competência: a da maior `valid_from` ≤ ela. Sem vigência → 0 (congelada)."""
    comp = first_of_month(competencia)
    vigente = ZERO
    for r in normalize_rates(rates):
        if r.valid_from <= comp:
            vigente = r.monthly_rate
        else:
            break
    return vigente


def build_ledger(
    *,
    principal: object,
    origin_month: date,
    through: date,
    rates: list[RateChange] | None = None,
    events: list[LedgerEvent] | None = None,
    payments: dict[date, object] | None = None,
    realized_through: date | None = None,
) -> list[LedgerLine]:
    """Monta o razão mês a mês, de `origin_month` até `through` (ambos inclusive).

    - `principal` / `origin_month`: o quanto e desde quando (no Endividamento, `valor_referencia`
      e `start_date` — reuso deliberado, sem coluna nova).
    - `rates`: vigências de taxa. Vazio = dívida congelada.
    - `events`: aportes, abatimentos e encargos manuais, por competência.
    - `payments`: {competência → pagamento REAL do mês}. Ausente = nada pago.
    - `realized_through`: última competência realizada; as posteriores saem marcadas como
      projeção. None = tudo realizado.

    Estender `through` para o futuro (sem pagamentos lá) é o que produz a PROJEÇÃO de saldo:
    onde a dívida estará se ninguém pagar nada.
    """
    p = _money(principal)
    if p < 0:
        raise ValueError("Principal não pode ser negativo.")
    start = first_of_month(origin_month)
    end = first_of_month(through)
    if end < start:
        raise ValueError("A competência final é anterior à origem da dívida.")

    ordered_rates = normalize_rates(list(rates or []))
    pays = {first_of_month(k): _money(v) for k, v in (payments or {}).items()}

    # Eventos agrupados por competência e por tipo (vários aportes no mesmo mês somam).
    by_month: dict[date, dict[str, Decimal]] = {}
    for ev in events or []:
        if ev.kind not in EVENT_KINDS:
            raise ValueError(f"Tipo de evento desconhecido: {ev.kind!r}.")
        amount = _money(ev.amount)
        if amount < 0:
            raise ValueError("Valor de evento não pode ser negativo (o sinal vem do tipo).")
        bucket = by_month.setdefault(first_of_month(ev.competencia), {})
        bucket[ev.kind] = bucket.get(ev.kind, ZERO) + amount

    lines: list[LedgerLine] = []
    saldo = p
    encargo_acumulado = ZERO

    for i in range(months_between(start, end) + 1):
        comp = add_months(start, i)
        movimentos = by_month.get(comp, {})
        aporte = movimentos.get(APORTE, ZERO)
        abatimento = movimentos.get(ABATIMENTO, ZERO)
        manual = movimentos.get(ENCARGO_MANUAL, ZERO)
        taxa = rate_for(comp, ordered_rates)

        # Regra 1: encargo sobre o saldo de ABERTURA, antes do aporte do mês.
        # Regra 5: saldo não-positivo não rende.
        encargo = _money(saldo * taxa) if saldo > 0 and taxa > 0 else ZERO
        encargo_acumulado = _money(encargo_acumulado + encargo)

        pagamento = pays.get(comp, ZERO)
        # Regra 3: o pagamento quita primeiro o encargo DO MÊS; o resto amortiza principal.
        juros_pagos = min(pagamento, encargo)
        amortizacao = _money(pagamento - juros_pagos)

        saldo_final = _money(saldo + aporte + manual + encargo - abatimento - pagamento)

        lines.append(
            LedgerLine(
                competencia=comp,
                saldo_inicial=saldo,
                aporte=aporte,
                abatimento=abatimento,
                encargo_manual=manual,
                taxa=taxa,
                encargo=encargo,
                pagamento=pagamento,
                juros_pagos=juros_pagos,
                amortizacao=amortizacao,
                saldo_final=saldo_final,
                encargo_acumulado=encargo_acumulado,
                is_projected=realized_through is not None and comp > first_of_month(realized_through),
            )
        )
        saldo = saldo_final

    return lines


def compute_indicators(lines: list[LedgerLine], *, principal: object) -> DebtIndicators:
    """Consolida o razão. `principal` é o mesmo passado ao `build_ledger` (dívida de origem).

    **Só as linhas REALIZADAS entram nos totais e no saldo atual.** Linha projetada é hipótese
    ("onde isso vai parar se ninguém pagar"), e somá-la faria o encargo já cobrado e o saldo de
    hoje incorporarem meses que ainda não aconteceram. A projeção sai à parte, em
    `saldo_projetado`.
    """
    p = _money(principal)
    realizadas = [ln for ln in lines if not ln.is_projected]
    projetadas = [ln for ln in lines if ln.is_projected]
    ultima_proj = projetadas[-1] if projetadas else None
    if not realizadas:
        return DebtIndicators(
            principal=p,
            total_aportes=ZERO,
            total_abatimentos=ZERO,
            total_encargos=ZERO,
            encargos_pagos=ZERO,
            encargos_capitalizados=ZERO,
            total_pago=ZERO,
            total_amortizado=ZERO,
            saldo_atual=p,
            taxa_vigente=ZERO,
            competencia_final=None,
            total_contratado=p,
            saldo_projetado=ultima_proj.saldo_final if ultima_proj else None,
            competencia_projecao=ultima_proj.competencia if ultima_proj else None,
        )

    def total(attr: str) -> Decimal:
        return _money(sum((getattr(ln, attr) for ln in realizadas), ZERO))

    encargos = total("encargo")
    pagos = total("juros_pagos")
    manuais = total("encargo_manual")
    aportes = total("aporte")
    ultima = realizadas[-1]

    return DebtIndicators(
        principal=p,
        total_aportes=aportes,
        total_abatimentos=total("abatimento"),
        total_encargos=encargos,
        encargos_pagos=pagos,
        # O que não virou caixa virou saldo — é a definição de capitalização.
        encargos_capitalizados=_money(encargos - pagos),
        total_pago=total("pagamento"),
        total_amortizado=total("amortizacao"),
        saldo_atual=ultima.saldo_final,
        taxa_vigente=ultima.taxa,
        competencia_final=ultima.competencia,
        total_contratado=_money(p + aportes + manuais),
        saldo_projetado=ultima_proj.saldo_final if ultima_proj else None,
        competencia_projecao=ultima_proj.competencia if ultima_proj else None,
    )


# --------------------------------------------------------------------------- #
# Planejador de parcelas — "quanto pagar por mês" quando o juro continua correndo
# --------------------------------------------------------------------------- #

#: Amortização fixa (SAC): abate o mesmo tanto de PRINCIPAL todo mês e paga o juro por cima.
#: A parcela CAI ao longo do tempo. É o que a planilha do financeiro fazia (coluna Amortização
#: fixa em 12.500 e "Pagto Parcela" caindo de 15.500 para 14.000).
MODE_AMORT_FIXA = "AMORT_FIXA"
#: Prestação fixa (Price): paga sempre o mesmo valor; o que muda é quanto dele vira amortização.
MODE_PARCELA_FIXA = "PARCELA_FIXA"
#: Quitar em N parcelas iguais: o sistema calcula a prestação.
MODE_N_PARCELAS = "N_PARCELAS"
PLAN_MODES = (MODE_AMORT_FIXA, MODE_PARCELA_FIXA, MODE_N_PARCELAS)

MAX_PLAN_MONTHS = 600


@dataclass(frozen=True)
class PlannedInstallment:
    competencia: date
    juros: Decimal
    amortizacao: Decimal
    #: O que efetivamente se paga no mês (juros + amortização).
    valor: Decimal
    saldo_final: Decimal


@dataclass(frozen=True)
class InstallmentPlan:
    parcelas: list[PlannedInstallment]
    total_pago: Decimal
    total_juros: Decimal

    @property
    def count(self) -> int:
        return len(self.parcelas)


def pmt(saldo: object, monthly_rate: object, n: int) -> Decimal:
    """Prestação fixa que quita `saldo` em `n` meses à taxa informada (Price).

    Taxa zero devolve a divisão simples — sem caso especial escondido no chamador.
    """
    s = _money(saldo)
    i = _rate(monthly_rate)
    if n < 1:
        raise ValueError("O número de parcelas deve ser pelo menos 1.")
    if i <= 0:
        return _money(s / n)
    f = (Decimal(1) + i) ** n
    return _money(s * i * f / (f - 1))


def plan_installments(
    *,
    saldo: object,
    start_month: date,
    rates: list[RateChange] | None = None,
    mode: str,
    amount: object | None = None,
    count: int | None = None,
) -> InstallmentPlan:
    """Calcula quanto pagar por mês para quitar um saldo com o juro ainda correndo.

    Responde a pergunta que o cronograma de parcelas fixas não responde: **quando o encargo
    continua incidindo, a parcela e a amortização são coisas diferentes**, e fixar uma faz a
    outra variar. Os três modos cobrem os acordos que aparecem na prática:

    - `AMORT_FIXA` (SAC): `amount` é quanto se abate de PRINCIPAL por mês; paga-se isso mais o
      juro do mês, então a parcela cai a cada mês. Foi o desenho do acordo original da planilha.
    - `PARCELA_FIXA` (Price): `amount` é quanto se paga por mês, fixo; a parte que amortiza
      cresce conforme o juro diminui.
    - `N_PARCELAS`: `count` é em quantos meses quitar; a prestação sai calculada.

    A taxa de cada mês vem das vigências (`rates`), então uma mudança de taxa no meio do plano é
    respeitada. No modo `N_PARCELAS` a prestação é calculada com a taxa do PRIMEIRO mês (é o que
    um credor faria ao fechar o acordo); se a taxa mudar depois, a última parcela absorve a
    diferença — por isso ela pode sair diferente das demais.

    A última parcela é sempre ajustada para zerar o saldo exatamente, sem sobra de centavos.
    """
    if mode not in PLAN_MODES:
        raise ValueError(f"Modo de parcelamento desconhecido: {mode!r}.")
    restante = _money(saldo)
    if restante <= 0:
        return InstallmentPlan(parcelas=[], total_pago=ZERO, total_juros=ZERO)

    ordered = normalize_rates(list(rates or []))
    inicio = first_of_month(start_month)

    #: Teto de parcelas: só o modo "quitar em N" tem número fechado de antemão.
    limite: int | None = None
    if mode == MODE_N_PARCELAS:
        if not count or int(count) < 1:
            raise ValueError("Informe em quantas parcelas quitar.")
        limite = int(count)
        alvo = pmt(restante, rate_for(inicio, ordered), limite)
    else:
        alvo = _money(amount if amount is not None else 0)
        if alvo <= 0:
            raise ValueError("Informe um valor maior que zero.")

    parcelas: list[PlannedInstallment] = []
    total_pago = ZERO
    total_juros = ZERO

    for offset in range(MAX_PLAN_MONTHS):
        if restante <= 0:
            break
        comp = add_months(inicio, offset)
        taxa = rate_for(comp, ordered)
        juros = _money(restante * taxa) if taxa > 0 else ZERO

        ultima = limite is not None and offset == limite - 1
        if ultima:
            # Fecha exato na parcela combinada: a prestação calculada quase nunca zera o saldo
            # no centavo, e criar uma parcela extra de R$ 0,02 seria pior do que ajustar esta.
            amortizacao = restante
            valor = _money(juros + amortizacao)
        elif mode == MODE_AMORT_FIXA:
            amortizacao = min(alvo, restante)
            valor = _money(juros + amortizacao)
        else:
            # Prestação fixa: o juro é servido primeiro; o que sobra amortiza. Uma parcela que
            # não cobre nem o juro do mês NUNCA quitaria a dívida — é erro de entrada, não um
            # plano longo, então recusar é mais honesto do que devolver 600 parcelas.
            if offset == 0 and alvo <= juros:
                raise ValueError(
                    f"A parcela de {alvo} não cobre nem o juro do primeiro mês ({juros}): "
                    "a dívida nunca seria quitada."
                )
            valor = min(alvo, _money(restante + juros))
            amortizacao = _money(valor - juros)

        restante = _money(restante - amortizacao)
        total_pago = _money(total_pago + valor)
        total_juros = _money(total_juros + juros)
        parcelas.append(
            PlannedInstallment(
                competencia=comp,
                juros=juros,
                amortizacao=amortizacao,
                valor=valor,
                saldo_final=restante,
            )
        )

    if restante > 0:
        raise ValueError(
            f"O plano não quita a dívida em {MAX_PLAN_MONTHS} meses — revise o valor da parcela."
        )
    return InstallmentPlan(parcelas=parcelas, total_pago=total_pago, total_juros=total_juros)
