"""Carga das cessões de crédito do Banco Daycoval (fev–jun/2026) como operações de antecipação.

Fonte: cartas de "Contrato de Cessão de Créditos sem Coobrigação" arquivadas em
~/Downloads/Operações Daycoval. Cada carta traz o valor de face por NF; o líquido
efetivamente creditado veio das anotações manuscritas conferidas nas próprias cartas
(duas delas já traziam o percentual escrito — 6,48% e 7,07% — e ambos batem com o
cálculo, o que valida a leitura).

Passa pela camada de serviço (create_batch → confirm_batch → set_actual_received), nunca
por SQL direto, para que as regras do perfil DAYCOVAL sejam aplicadas: valor antecipado
MANUAL por NF, liquidação das NFs como RECEBIDAS e previsto×realizado preservados.

NÃO carregadas (dados insuficientes, confirmar antes de incluir):
  - cessão de 12/03 (crédito 13/03), NFs 3365–3369: líquido creditado não anotado;
  - cessão de 26/03 (crédito 27/03), NF 3370: líquido creditado não anotado;
  - cessão de 26/05 (crédito 29/05), NF 3397: manuscrito ambíguo (58.163,80 ou 68.163,80).

Uso:
    python3 scripts/load_daycoval_cessions.py --dry-run
    python3 scripts/load_daycoval_cessions.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date

from sqlalchemy import select

from app.database.session import AsyncSessionLocal
from app.models.advance_institution import AdvanceInstitution
from app.models.receivable import ReceivableInvoice
from app.services.receivable_advance_batch_service import ReceivableAdvanceBatchService

INSTITUTION_NAME = "Banco Daycoval"
LOG_USER = "carga-daycoval"

# (data do crédito, rótulo do contrato, {nº NF: face cedida}, líquido efetivamente creditado)
CESSIONS: list[tuple[date, str, dict[str, float], float]] = [
    (
        date(2026, 2, 8),
        "Cessão de 05/02/2026",
        {"3360": 37_983.21, "3363": 54_850.25},
        86_851.12,
    ),
    (
        date(2026, 4, 2),
        "Cessão de 31/03/2026",
        {
            "3376": 57_715.32,
            "3377": 13_339.86,
            "3378": 17_105.40,
            "3379": 23_595.39,
            "3380": 177_354.29,
        },
        269_079.22,
    ),
    (
        date(2026, 5, 8),
        "Cessão de 06/05/2026",
        {
            "3383": 57_750.20,
            "3387": 26_161.20,
            "3388": 28_240.68,
            "3389": 72_280.28,
            "3390": 13_067.62,
            "3391": 192_687.51,
        },
        365_575.21,
    ),
    (
        date(2026, 5, 22),
        "Cessão de 20/05/2026",
        {"3398": 68_605.01},
        63_623.15,
    ),
    (
        date(2026, 6, 3),
        "Cessão de 01/06/2026",
        {
            "3394": 7_461.72,
            "3395": 14_923.43,
            "3396": 14_923.43,
            "3399": 22_868.34,
            "3400": 22_790.43,
            "3401": 31_913.31,
        },
        107_439.07,
    ),
    (
        date(2026, 6, 12),
        "Cessão de 09/06/2026",
        {"3402": 43_478.08, "3405": 187_327.60},
        214_478.81,
    ),
]


async def run(apply: bool) -> int:
    async with AsyncSessionLocal() as db:
        inst = (
            await db.execute(select(AdvanceInstitution).where(AdvanceInstitution.name == INSTITUTION_NAME))
        ).scalar_one_or_none()
        if inst is None:
            print(f"ERRO: instituição '{INSTITUTION_NAME}' não cadastrada.")
            return 1
        if (inst.operation_profile or "").upper() != "DAYCOVAL":
            print(f"ERRO: perfil inesperado para '{INSTITUTION_NAME}': {inst.operation_profile}")
            return 1

        svc = ReceivableAdvanceBatchService(db)
        total_face = total_net = 0.0
        problems: list[str] = []

        for receive_date, label, faces, net_received in CESSIONS:
            nums = list(faces)
            found = {
                inv.nf_number: inv
                for inv in (
                    await db.execute(select(ReceivableInvoice).where(ReceivableInvoice.nf_number.in_(nums)))
                ).scalars()
            }
            missing = [n for n in nums if n not in found]
            if missing:
                problems.append(f"{label}: NFs não encontradas — {', '.join(missing)}")
                continue

            face = round(sum(faces.values()), 2)
            cost = round(face - net_received, 2)
            pct = (cost / face) * 100 if face else 0.0
            total_face += face
            total_net += net_received

            print(
                f"{label:<24} crédito {receive_date:%d/%m/%Y}  {len(nums)} NFs  "
                f"face {face:>12,.2f}  líquido {net_received:>12,.2f}  deságio {cost:>10,.2f} ({pct:5.2f}%)"
            )

            if not apply:
                continue

            items_config = [
                {"invoice_id": found[n].id, "advance_basis": "MANUAL", "advanced_amount": faces[n]}
                for n in nums
            ]
            batch = await svc.create_batch(
                operation_type="BORDERO",
                operation_code=None,  # a Daycoval não fornece número de operação
                institution=inst.name,
                institution_id=inst.id,
                receive_date=receive_date,
                repayment_date=None,
                observation=f"{label} — carga a partir da carta de cessão de crédito.",
                items_config=items_config,
                repasse_enabled=False,
                created_by_id=None,
                log_user=LOG_USER,
            )
            await svc.confirm_batch(batch_id=batch.id, log_user=LOG_USER)
            # Realizado informado à parte: preserva o previsto (= face cedida) e faz o
            # deságio implícito aparecer como previsto − realizado.
            await svc.set_actual_received(batch_id=batch.id, actual=net_received, log_user=LOG_USER)
            print(f"{'':<24} → operação SGC {batch.sgc_number} criada e confirmada")

        if problems:
            print("\n".join(["", "PROBLEMAS:", *problems]))
            if apply:
                await db.rollback()
                print("\nNada foi gravado (rollback).")
                return 1

        cost = round(total_face - total_net, 2)
        print(
            f"\n{'TOTAL':<24} {len(CESSIONS)} cessões  face {total_face:>12,.2f}  "
            f"líquido {total_net:>12,.2f}  deságio {cost:>10,.2f} ({cost / total_face * 100:5.2f}%)"
        )

        if apply:
            await db.commit()
            print("\nGravado.")
        else:
            await db.rollback()
            print("\nSimulação — nada foi gravado. Use --apply para gravar.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="apenas simula")
    g.add_argument("--apply", action="store_true", help="grava no banco")
    args = ap.parse_args()
    sys.exit(asyncio.run(run(apply=args.apply)))
