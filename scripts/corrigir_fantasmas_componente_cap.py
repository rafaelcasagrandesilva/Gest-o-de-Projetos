#!/usr/bin/env python3
"""Limpa os títulos fantasma que a MUDANÇA DE FORMATO DOS COMPONENTES deixou no CAP.

O CÓDIGO já foi corrigido (`sync_collaborator_payables_for_labor` agora adota o título
existente nos DOIS sentidos). Isto aqui só limpa o que ficou para trás.

O DEFEITO
    Zerar a ajuda de custo de um PJ no cadastro funde os dois componentes da folha
    ("Salário Base PJ" + "Ajuda de Custo PJ") numa única linha SEM rótulo. A
    sincronização casava o título pelo RÓTULO e só sabia adotar no sentido
    "sem rótulo → com rótulo". No sentido inverso ela não encontrava par, concluía que
    o título não existia e criava um segundo, EM ABERTO, ao lado do que já estava PAGO —
    que a limpeza de órfãos, corretamente, nunca apaga.

ASSINATURA DO PAR (mesmo colaborador, mês e projeto)
    - PAGA   → nome COM rótulo de componente, mesmo valor  (é a verdadeira, tem o dinheiro)
    - ABERTA → nome SEM rótulo, sem nenhum pagamento       (é a fantasma)

REPARO
    Apaga a fantasma e renomeia a paga para o nome sem rótulo — exatamente o desfecho que
    a sincronização corrigida produz sozinha na próxima vez que rodar. Fazer aqui evita
    que o nome mude sozinho depois, sem ninguém entender por quê.

SEGURANÇA
    Nunca toca em título com qualquer pagamento (nem parcial), em título protegido
    (valor editado à mão, conciliado, ajuste manual) nem em título de outro tipo.

Uso:
    python scripts/corrigir_fantasmas_componente_cap.py            # simulação (padrão)
    python scripts/corrigir_fantasmas_componente_cap.py --apply    # grava

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

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType  # noqa: E402
from app.services.payable_snapshot_service import (  # noqa: E402
    _collaborator_payable_component_label,
    _payable_row_is_dynamic_sync_protected,
)


def _money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


async def reparar_fantasmas(session, *, apply: bool, competencia: date | None = None) -> dict:
    stmt = select(PayableSnapshot).where(
        PayableSnapshot.type == PayableSnapshotType.COLLABORATOR,
        PayableSnapshot.is_obsolete.is_(False),
    )
    if competencia is not None:
        stmt = stmt.where(PayableSnapshot.month == competencia)
    rows = list((await session.execute(stmt)).scalars().all())

    # Agrupa por (mês, colaborador, projeto) — o mesmo recorte que a sincronização usa.
    grupos: dict[tuple, list[PayableSnapshot]] = defaultdict(list)
    for r in rows:
        grupos[(r.month, r.ref_id, r.project_id)].append(r)

    apagados = 0
    renomeados = 0
    revisar: list[str] = []

    for (mes, _ref, _proj), linhas in sorted(grupos.items(), key=lambda kv: str(kv[0][0])):
        sem_rotulo = [x for x in linhas if not _collaborator_payable_component_label(x.name)]
        com_rotulo = [x for x in linhas if _collaborator_payable_component_label(x.name)]
        if not sem_rotulo or not com_rotulo:
            continue  # formato homogêneo: nada a fazer

        for fantasma in sem_rotulo:
            if _money(fantasma.amount_paid) > 0:
                revisar.append(f"{mes} {fantasma.name!r} sem rótulo MAS com pagamento — revise à mão")
                continue
            if _payable_row_is_dynamic_sync_protected(fantasma):
                revisar.append(f"{mes} {fantasma.name!r} protegido (valor editado/conciliado) — revise à mão")
                continue
            # A verdadeira: mesma quantia, com rótulo e com dinheiro.
            paga = next(
                (
                    c
                    for c in com_rotulo
                    if _money(c.amount_final) == _money(fantasma.amount_final)
                    and _money(c.amount_paid) > 0
                ),
                None,
            )
            if paga is None:
                revisar.append(
                    f"{mes} {fantasma.name!r} ({_money(fantasma.amount_final)}) sem par pago de mesmo valor — revise à mão"
                )
                continue

            print(f"  [apagar]   {mes} {fantasma.name!r} R$ {_money(fantasma.amount_final)} (em aberto)")
            if apply:
                await session.delete(fantasma)
            apagados += 1

            novo_nome = str(fantasma.name)
            if paga.name != novo_nome:
                print(f"  [renomear] {mes} {paga.name!r} → {novo_nome!r} (paga, R$ {_money(paga.amount_paid)})")
                if apply:
                    paga.name = novo_nome
                renomeados += 1

    return {"apagados": apagados, "renomeados": renomeados, "revisar": revisar}


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="grava (padrão: só simula)")
    ap.add_argument("--competencia", metavar="AAAA-MM", help="limita a UM mês do CAP (ex.: 2026-08)")
    args = ap.parse_args()

    comp = None
    if args.competencia:
        try:
            ano, mes = str(args.competencia).split("-")
            comp = date(int(ano), int(mes), 1)
        except (ValueError, AttributeError):
            print("Competência inválida — use AAAA-MM (ex.: 2026-08).", file=sys.stderr)
            return 2

    url = os.environ.get("DATABASE_URL")
    if not url:
        from app.core.config import settings

        url = settings.database_url
    engine = create_async_engine(url)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    modo = "APLICANDO" if args.apply else "SIMULAÇÃO (nada será gravado)"
    print(f"Fantasmas por mudança de formato de componente — {modo}")
    print(f"Banco: ...{url[-40:]}")
    print(f"Mês: {comp or 'todos'}\n")

    async with Session() as session:
        res = await reparar_fantasmas(session, apply=args.apply, competencia=comp)
        if args.apply:
            await session.commit()
    await engine.dispose()

    print(f"\nTítulos fantasma apagados: {res['apagados']}")
    print(f"Títulos pagos renomeados:  {res['renomeados']}")
    if res["revisar"]:
        print(f"\nPARA REVISAR À MÃO ({len(res['revisar'])}):")
        for m in res["revisar"]:
            print(f"  - {m}")
    if not args.apply and (res["apagados"] or res["renomeados"]):
        print("\nNada foi gravado. Rode de novo com --apply para efetivar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
