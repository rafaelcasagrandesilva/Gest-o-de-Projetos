#!/usr/bin/env python3
"""Simulador do motor de saldo do Endividamento — para conferir números à mão, no terminal.

Roda o núcleo puro (`app/services/debt_accrual.py`) sem banco, sem tela e sem tocar em nada:
serve para validar o comportamento antes de a Fase 2 plugar o motor no sistema.

Sem argumento nenhum, roda a PLANILHA REAL do acordo com o fornecedor e compara linha a linha
com os saldos que a planilha mostra:

    ./.venv/bin/python scripts/simular_divida.py

Para simular um caso seu, monte a dívida pelos argumentos (mês sempre AAAA-MM):

    ./.venv/bin/python scripts/simular_divida.py \
        --principal 50000 --inicio 2026-01 --ate 2027-12 \
        --taxa 2026-01=0.005 --taxa 2026-07=0 \
        --aporte 2026-03=10000 \
        --pagamento 2026-05=2500 --pagamento 2026-06=2500

Taxa é decimal ao mês: 0.005 = 0,5% a.m. (o padrão proposto para o SGC), 0.03 = 3% a.m.
Uma vigência com taxa 0 CONGELA a dívida a partir daquele mês — é assim que se representa
um acordo fechado, que para de correr encargo.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.debt_accrual import (  # noqa: E402
    ABATIMENTO,
    APORTE,
    ENCARGO_MANUAL,
    LedgerEvent,
    RateChange,
    build_ledger,
    compute_indicators,
)

# ---------------------------------------------------------------------------
# O caso real (planilha do acordo com o fornecedor, 04/2024 a 07/2026)
# ---------------------------------------------------------------------------
PLANILHA_SALDOS = [
    "87500.00", "75000.00", "62500.00", "50000.00", "37500.00", "38625.00", "39783.75",
    "40977.26", "42206.58", "71472.78", "73616.96", "75825.47", "78100.23", "80443.24",
    "82856.54", "85342.23", "147902.50", "152339.58", "156909.76", "61617.06", "63465.57",
    "64417.55", "65383.82", "66364.57", "67360.04", "68370.44", "69396.00", "70436.94",
]


def mes(texto: str) -> date:
    """AAAA-MM -> primeiro dia do mês."""
    try:
        ano, m = texto.strip().split("-")
        return date(int(ano), int(m), 1)
    except Exception as exc:  # noqa: BLE001
        raise argparse.ArgumentTypeError(f"Mês inválido: {texto!r} (use AAAA-MM).") from exc


def par(texto: str) -> tuple[date, Decimal]:
    """AAAA-MM=valor -> (mês, valor)."""
    if "=" not in texto:
        raise argparse.ArgumentTypeError(f"Use AAAA-MM=valor (recebido: {texto!r}).")
    m, valor = texto.split("=", 1)
    return mes(m), Decimal(valor.strip().replace(",", "."))


def brl(v: Decimal) -> str:
    inteiro, _, centavos = f"{v:.2f}".partition(".")
    negativo = inteiro.startswith("-")
    inteiro = inteiro.lstrip("-")
    grupos = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)
    return ("-" if negativo else "") + ".".join(grupos) + "," + centavos


def pct(taxa: Decimal) -> str:
    return f"{taxa * 100:.4f}".rstrip("0").rstrip(".") + "%"


def main() -> int:
    p = argparse.ArgumentParser(
        description="Simula a evolução de uma dívida (motor de saldo do Endividamento).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--principal", type=Decimal, help="Valor de origem da dívida.")
    p.add_argument("--inicio", type=mes, help="Competência de origem (AAAA-MM).")
    p.add_argument("--ate", type=mes, help="Última competência a calcular (AAAA-MM).")
    p.add_argument("--realizado-ate", type=mes, help="A partir daí as linhas saem como projeção.")
    p.add_argument("--taxa", type=par, action="append", default=[], metavar="AAAA-MM=0.005",
                   help="Vigência de taxa mensal. Repetível. 0 congela a dívida.")
    p.add_argument("--aporte", type=par, action="append", default=[], metavar="AAAA-MM=VALOR",
                   help="Dívida nova contratada no mês. Repetível.")
    p.add_argument("--pagamento", type=par, action="append", default=[], metavar="AAAA-MM=VALOR",
                   help="Pagamento realizado no mês. Repetível.")
    p.add_argument("--abatimento", type=par, action="append", default=[], metavar="AAAA-MM=VALOR",
                   help="Perdão/desconto negociado (reduz saldo sem ser caixa). Repetível.")
    p.add_argument("--encargo", type=par, action="append", default=[], metavar="AAAA-MM=VALOR",
                   help="Multa/honorário lançado à mão. Repetível.")
    args = p.parse_args()

    usando_planilha = args.principal is None and not args.taxa and not args.pagamento
    if usando_planilha:
        principal = Decimal("100000.00")
        inicio, ate = date(2024, 4, 1), date(2026, 7, 1)
        taxas = [RateChange(date(2024, 4, 1), Decimal("0.03")),
                 RateChange(date(2026, 1, 1), Decimal("0.015"))]
        eventos = [LedgerEvent(date(2025, 1, 1), APORTE, Decimal("28000")),
                   LedgerEvent(date(2025, 8, 1), APORTE, Decimal("60000"))]
        pagamentos = {date(2024, 4, 1): Decimal("15500"), date(2024, 5, 1): Decimal("15125"),
                      date(2024, 6, 1): Decimal("14750"), date(2024, 7, 1): Decimal("14375"),
                      date(2024, 8, 1): Decimal("14000"), date(2025, 11, 1): Decimal("100000")}
        print("\n\033[1mCASO REAL — acordo com fornecedor (planilha do financeiro)\033[0m")
        print("Rode com --help para simular uma dívida sua.\n")
    else:
        if args.principal is None or args.inicio is None:
            p.error("--principal e --inicio são obrigatórios ao simular uma dívida própria.")
        principal, inicio = args.principal, args.inicio
        ate = args.ate or inicio
        taxas = [RateChange(m, v) for m, v in args.taxa]
        eventos = (
            [LedgerEvent(m, APORTE, v) for m, v in args.aporte]
            + [LedgerEvent(m, ABATIMENTO, v) for m, v in args.abatimento]
            + [LedgerEvent(m, ENCARGO_MANUAL, v) for m, v in args.encargo]
        )
        pagamentos = dict(args.pagamento)
        print()

    linhas = build_ledger(
        principal=principal, origin_month=inicio, through=ate,
        rates=taxas, events=eventos, payments=pagamentos,
        realized_through=args.realizado_ate,
    )

    cab = (f"{'#':>3} {'MÊS':>8} {'SALDO INICIAL':>15} {'APORTE':>12} {'TAXA':>8} "
           f"{'ENCARGO':>12} {'PAGAMENTO':>13} {'JUROS':>11} {'AMORTIZ.':>13} {'SALDO FINAL':>15}")
    print(cab)
    print("-" * len(cab))
    for i, ln in enumerate(linhas, start=1):
        marca = " ·proj" if ln.is_projected else ""
        linha = (f"{i:>3} {ln.competencia.strftime('%m/%Y'):>8} {brl(ln.saldo_inicial):>15} "
                 f"{brl(ln.aporte):>12} {pct(ln.taxa):>8} {brl(ln.encargo):>12} "
                 f"{brl(ln.pagamento):>13} {brl(ln.juros_pagos):>11} "
                 f"{brl(ln.amortizacao):>13} {brl(ln.saldo_final):>15}{marca}")
        if usando_planilha:
            dif = ln.saldo_final - Decimal(PLANILHA_SALDOS[i - 1])
            linha += "" if dif == 0 else f"   planilha {PLANILHA_SALDOS[i-1]} (dif {dif})"
        print(linha)

    ind = compute_indicators(linhas, principal=principal)
    print("\n\033[1mRESUMO\033[0m")
    print(f"  Principal de origem ............ R$ {brl(ind.principal):>14}")
    if ind.total_aportes:
        print(f"  Aportes (dívida nova) .......... R$ {brl(ind.total_aportes):>14}")
    if ind.total_abatimentos:
        print(f"  Abatimentos negociados ......... R$ {brl(ind.total_abatimentos):>14}")
    print(f"  Total contratado ............... R$ {brl(ind.total_contratado):>14}")
    print(f"  Encargos cobrados .............. R$ {brl(ind.total_encargos):>14}")
    print(f"    · viraram caixa (pagos) ...... R$ {brl(ind.encargos_pagos):>14}")
    print(f"    · viraram saldo (capitaliz.) . R$ {brl(ind.encargos_capitalizados):>14}")
    print(f"  Pago ao credor ................. R$ {brl(ind.total_pago):>14}")
    print(f"    · amortizou principal ........ R$ {brl(ind.total_amortizado):>14}")
    print(f"  Taxa vigente no fim ............ {pct(ind.taxa_vigente):>17}")
    print(f"  \033[1mSaldo em {ind.competencia_final:%m/%Y} ............... R$ {brl(ind.saldo_atual):>14}\033[0m")

    if usando_planilha:
        maior = max((abs(ln.saldo_final - Decimal(PLANILHA_SALDOS[i]))
                     for i, ln in enumerate(linhas)), default=Decimal("0"))
        print(f"\n  Maior divergência contra a planilha: R$ {brl(maior)} "
              f"(arredondamento da planilha; o motor arredonda a cada mês)")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
