#!/usr/bin/env python3
"""Corrige os resíduos que os defeitos de ago/2026 deixaram no Contas a Pagar.

O CÓDIGO já foi corrigido — isto aqui só limpa o que ficou para trás. Dois reparos
independentes, ambos idempotentes:

1. TÍTULOS FANTASMA POR RENOMEAÇÃO
   A sincronização de mão de obra casava o título pelo NOME. Ao corrigir o nome de um
   colaborador no cadastro, ela não reconhecia o título já PAGO e criava um segundo,
   EM ABERTO, ao lado. Assinatura do par (mesmo colaborador, mês, projeto e componente):
     - PAGA    → nome ANTIGO  (é a verdadeira, tem o pagamento)
     - ABERTA  → nome ATUAL   (é a fantasma, nasceu da renomeação)
   Reparo: apaga a fantasma e renomeia a paga para o nome atual — o mesmo desfecho que
   a correção do código produz hoje.

2. VEÍCULOS COM COMBUSTÍVEL NULO NO REALIZADO
   A Inicializar Competência copiava o combustível do PREVISTO, onde ele é sempre nulo.
   A linha nascia num estado que a própria API recusa, e a tela não deixava editar.
   Reparo: nulo → 0,00 (valor válido e editável, que é como a cópia passa a nascer).
   NÃO recalcula o custo mensal: o combustível real ainda vai ser digitado.

Uso:
    python scripts/corrigir_residuos_cap_ago2026.py            # simulação (padrão)
    python scripts/corrigir_residuos_cap_ago2026.py --apply    # grava

Aponte DATABASE_URL para o banco alvo. Faça backup antes de rodar com --apply.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402


def _money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


async def reparar_titulos_fantasma(session, *, apply: bool, competencia=None) -> dict:
    """Par (paga com nome antigo, aberta com nome atual) → fica só a paga, renomeada."""
    from app.services.payable_snapshot_service import _collaborator_payable_component_label

    rows = (
        await session.execute(
            text(
                """
                select s.id, s.name, s.month, s.project_id, s.ref_id,
                       s.amount_final, s.amount_paid, s.paid,
                       e.full_name nome_atual,
                       (select count(*) from payable_payments pp
                         where pp.payable_snapshot_id = s.id) n_pagamentos
                  from payable_snapshots s
                  join employees e on e.id = s.ref_id
                 where s.type = 'COLLABORATOR'
                   and (cast(:comp as date) is null or s.month = cast(:comp as date))
                 order by s.month, s.ref_id
                """
            ),
            {"comp": competencia},
        )
    ).all()

    # Agrupa pelo que identifica de fato o título, INDEPENDENTE do nome da pessoa.
    grupos: dict[tuple, list] = defaultdict(list)
    for r in rows:
        chave = (r.ref_id, r.month, r.project_id, _collaborator_payable_component_label(r.name))
        grupos[chave].append(r)

    apagados, renomeados, para_revisar = 0, 0, []
    for chave, itens in grupos.items():
        if len(itens) < 2:
            continue
        nome_atual = itens[0].nome_atual
        pagas = [i for i in itens if _money(i.amount_paid) > 0]
        fantasmas = [
            i
            for i in itens
            if _money(i.amount_paid) == 0
            and i.n_pagamentos == 0
            and not i.paid
            and str(i.name).startswith(str(nome_atual))
        ]
        if len(pagas) != 1 or not fantasmas:
            continue
        paga = pagas[0]
        if str(paga.name).startswith(str(nome_atual)):
            continue  # a paga já está com o nome atual — não é o caso da renomeação

        for f in fantasmas:
            if _money(f.amount_final) != _money(paga.amount_final):
                # Valores diferentes podem ser um ajuste real: não decide sozinho.
                para_revisar.append(
                    (f.month, nome_atual, float(f.amount_final), float(paga.amount_final))
                )
                continue
            print(
                f"  [fantasma] {f.month} {f.name!r} R$ {f.amount_final} "
                f"→ apagar (paga: {paga.name!r})"
            )
            if apply:
                await session.execute(
                    text("delete from payable_snapshots where id = :i"), {"i": f.id}
                )
            apagados += 1

        novo_nome = _renomear(paga.name, nome_atual)
        if novo_nome != paga.name:
            print(f"  [renomear] {paga.month} {paga.name!r} → {novo_nome!r}")
            if apply:
                await session.execute(
                    text("update payable_snapshots set name = :n where id = :i"),
                    {"n": novo_nome, "i": paga.id},
                )
            renomeados += 1

    return {"apagados": apagados, "renomeados": renomeados, "revisar": para_revisar}


def _renomear(nome_titulo: str, nome_atual: str) -> str:
    """Troca só a parte do NOME, preservando o rótulo do componente."""
    _head, sep, tail = str(nome_titulo).rpartition(" — ")
    return f"{nome_atual} — {tail}" if sep else str(nome_atual)


async def reparar_combustivel_nulo(session, *, apply: bool, competencia=None) -> int:
    from app.models.project_operational import ProjectVehicle

    stmt = select(ProjectVehicle).where(
        ProjectVehicle.scenario == text("'REALIZADO'"),
        ProjectVehicle.fuel_cost_realized.is_(None),
    )
    if competencia is not None:
        stmt = stmt.where(ProjectVehicle.competencia == competencia)
    rows = list((await session.execute(stmt)).scalars().all())
    for r in rows:
        print(f"  [combustível] veículo {r.vehicle_id} competência {r.competencia} → 0,00")
        if apply:
            r.fuel_cost_realized = Decimal("0")
    return len(rows)


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="grava (padrão: só simula)")
    ap.add_argument(
        "--competencia",
        metavar="AAAA-MM",
        help="limita a UMA competência (ex.: 2026-01) — permite conferir mês a mês",
    )
    ap.add_argument(
        "--etapa",
        choices=("fantasmas", "veiculos", "todas"),
        default="todas",
        help="roda só uma das etapas (padrão: todas)",
    )
    args = ap.parse_args()
    comp = None
    if args.competencia:
        try:
            ano, mes = str(args.competencia).split("-")
            comp = date(int(ano), int(mes), 1)
        except (ValueError, AttributeError):
            print("Competência inválida — use AAAA-MM (ex.: 2026-01).", file=sys.stderr)
            return 2

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("Defina DATABASE_URL.", file=sys.stderr)
        return 2

    engine = create_async_engine(url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    modo = "APLICANDO" if args.apply else "SIMULAÇÃO (nada será gravado)"
    escopo = f"competência {comp}" if comp else "todas as competências"
    print(f"Banco: {url.rsplit('/', 1)[-1]}  |  Modo: {modo}  |  Escopo: {escopo}\n")

    r1 = {"apagados": 0, "renomeados": 0, "revisar": []}
    n2 = 0
    async with Session() as s:
        if args.etapa in ("fantasmas", "todas"):
            print("1) Títulos fantasma criados por renomeação de colaborador")
            r1 = await reparar_titulos_fantasma(s, apply=args.apply, competencia=comp)
        if args.etapa in ("veiculos", "todas"):
            print("\n2) Veículos REALIZADO com combustível nulo")
            n2 = await reparar_combustivel_nulo(s, apply=args.apply, competencia=comp)
        if args.apply:
            await s.commit()

    print("\n" + "=" * 62)
    print(f"  Títulos fantasma apagados ....... {r1['apagados']}")
    print(f"  Títulos pagos renomeados ........ {r1['renomeados']}")
    print(f"  Veículos com combustível zerado .. {n2}")
    if r1["revisar"]:
        print(f"\n  ATENÇÃO — {len(r1['revisar'])} par(es) com VALORES DIFERENTES não tocados;")
        print("  precisam de decisão humana (pode ser ajuste real, não duplicata):")
        for mes, nome, v_aberta, v_paga in r1["revisar"]:
            print(f"    {mes}  {nome}: aberta R$ {v_aberta} × paga R$ {v_paga}")
    if not args.apply:
        print("\n  Simulação. Rode de novo com --apply para gravar.")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
