#!/usr/bin/env python3
"""Move lançamentos avulsos de um item de Custo Fixo para Componentes Variáveis (Reembolso).

POR QUE
    O item "Paulo Arieiro" (Custos Indiretos) é a Retirada de Capital do sócio, mas em
    out–nov/2026 recebeu lançamentos extras que são REEMBOLSOS (materiais, combustível,
    notebook). Com o item vinculado ao colaborador como "— Retirada de Capital", esses
    lançamentos sairiam no Contas a Pagar com o rótulo errado. O lugar deles é o componente
    variável "Reembolso" do mesmo item: título "<Colaborador> — Reembolso", fora da média.

O QUE FAZ (por lançamento selecionado)
    1. cria o componente variável (tipo Reembolso, mesma competência, mesmo valor, nota =
       descrição do lançamento) — o serviço já materializa o título VARIABLE no CAP;
    2. apaga o título ABERTO do lançamento e o próprio lançamento da grade.

SELEÇÃO
    Lançamentos do item com DESCRIÇÃO preenchida (o lançamento principal do mês, sem
    descrição, nunca é tocado). Opcional: --desde AAAA-MM.

SEGURANÇA
    Lançamento cujo título tem qualquer pagamento (nem parcial) é PULADO e listado para
    revisão. Exige que o item já esteja vinculado a um colaborador (o componente herda o
    colaborador do item). Tudo numa transação; simulação por padrão.

Uso:
    python scripts/mover_lancamentos_para_reembolso.py --item <uuid>            # simulação
    python scripts/mover_lancamentos_para_reembolso.py --item <uuid> --apply    # grava

Aponte DATABASE_URL para o banco alvo. Faça backup antes de rodar com --apply.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date
from uuid import UUID

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.models.company_finance import CompanyFinancialItem, CompanyFinancialPayment  # noqa: E402
from app.models.payable_snapshot import PayableSnapshot  # noqa: E402
from app.models.payment_component import PaymentComponentType  # noqa: E402
from app.services.payable_snapshot_service import _has_active_payments, _money2  # noqa: E402
from app.services.payment_variable_component_service import PaymentVariableComponentService  # noqa: E402

REEMBOLSO_CODE = "reembolso"


async def mover(
    session: AsyncSession, *, item_id: UUID, desde: date | None, apply: bool
) -> dict:
    item = await session.get(CompanyFinancialItem, item_id)
    if item is None:
        raise SystemExit(f"Item {item_id} não encontrado.")
    if item.employee_id is None:
        raise SystemExit("O item ainda não está vinculado a um colaborador — vincule antes (Editar estrutura).")
    tipo = (
        await session.execute(select(PaymentComponentType).where(PaymentComponentType.code == REEMBOLSO_CODE))
    ).scalar_one_or_none()
    if tipo is None:
        raise SystemExit("Tipo de componente 'reembolso' não encontrado.")

    q = select(CompanyFinancialPayment).where(
        CompanyFinancialPayment.item_id == item_id,
        CompanyFinancialPayment.descricao.is_not(None),
        CompanyFinancialPayment.descricao != "",
    )
    if desde is not None:
        q = q.where(CompanyFinancialPayment.competencia >= desde)
    entries = (await session.execute(q.order_by(CompanyFinancialPayment.competencia))).scalars().all()

    svc = PaymentVariableComponentService(session)
    res = {"movidos": [], "revisar": []}
    print(f"Item: {item.nome} ({item.id})\n")
    for e in entries:
        titulos = (
            await session.execute(select(PayableSnapshot).where(PayableSnapshot.entry_id == e.id))
        ).scalars().all()
        pago = False
        for t in titulos:
            if _money2(t.amount_paid) > 0 or await _has_active_payments(session, snapshot_id=t.id):
                pago = True
        linha = f"{e.competencia:%Y-%m}  R$ {float(e.valor):>10,.2f}  {e.descricao}"
        if pago:
            res["revisar"].append(f"{linha}  (título com pagamento — não movido)")
            continue
        print(f"  mover → Reembolso: {linha}")
        res["movidos"].append(linha)
        if not apply:
            continue
        await svc.create(
            {
                "type_id": tipo.id,
                "company_financial_item_id": item.id,
                "competencia": e.competencia,
                "amount": e.valor,
                "note": e.descricao,
            }
        )
        for t in titulos:
            await session.delete(t)
        await session.flush()
        await session.delete(e)
        await session.flush()
    return res


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--item", required=True, help="id do item de Custo Fixo")
    ap.add_argument("--desde", metavar="AAAA-MM", help="só lançamentos a partir desta competência")
    ap.add_argument("--apply", action="store_true", help="grava (padrão: só simula)")
    args = ap.parse_args()

    desde = None
    if args.desde:
        ano, mes = args.desde.split("-")
        desde = date(int(ano), int(mes), 1)

    url = os.environ.get("DATABASE_URL")
    if not url:
        from app.core.config import settings

        url = settings.database_url
    engine = create_async_engine(url)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    print(f"Lançamentos → Reembolso — {'APLICANDO' if args.apply else 'SIMULAÇÃO (nada será gravado)'}")
    print(f"Banco: ...{url[-40:]}\n")
    async with Session() as session:
        res = await mover(session, item_id=UUID(args.item), desde=desde, apply=args.apply)
        if args.apply:
            await session.commit()
    await engine.dispose()

    print(f"\nMovidos: {len(res['movidos'])}")
    if res["revisar"]:
        print(f"\nPARA REVISAR À MÃO ({len(res['revisar'])}):")
        for m in res["revisar"]:
            print(f"  - {m}")
    if not args.apply and res["movidos"]:
        print("\nNada foi gravado. Rode de novo com --apply para efetivar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
