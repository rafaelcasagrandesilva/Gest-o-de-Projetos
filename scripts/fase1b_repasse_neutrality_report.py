"""Relatório de neutralidade da Fase 1B (Repasse: CAP → Ledger). SOMENTE LEITURA.

Certifica que a migração do Repasse do Contas a Pagar para o Ledger **não alterou valor algum**:
o que antes estava no CAP passou a estar no Ledger, real por real, por instituição e por competência.

Fonte da verdade (ESPERADO) = `repasse_amount` congelado de cada operação confirmada (OPEN/SETTLED)
com `repasse_enabled`. Compara com o que o Ledger registra (créditos de OPERATION) e com o que
sobrou no CAP (apenas repasse PAGO, preservado + compensado por DEBIT ADJUSTMENT).

A Fase 1B só é considerada concluída se a DIFERENÇA for **zero** em todos os cortes.

Uso:  python -m scripts.fase1b_repasse_neutrality_report   (exit 0 = APROVADO, 1 = REPROVADO)
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select

from app.database.session import AsyncSessionLocal, engine
from app.models.advance_institution import AdvanceInstitution
from app.models.advance_repasse_ledger import (
    AdvanceRepasseLedgerEntry,
    RepasseLedgerDirection,
    RepasseLedgerSource,
)
from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
from app.models.receivable_advance_batch import CONFIRMED_BATCH_STATUSES, ReceivableAdvanceBatch

_C = Decimal("0.01")


def m(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(_C)


def _fmt_bucket(title: str, d: dict) -> None:
    for k, v in sorted(d.items(), key=lambda kv: str(kv[0])):
        print(f"       {title} {str(k):<28} {v}")


async def main() -> int:
    await engine.dispose()
    async with AsyncSessionLocal() as s:
        insts = {i.id: i for i in (await s.execute(select(AdvanceInstitution))).scalars().all()}

        def inst_name(bid):
            return insts[bid].name if bid in insts else str(bid)

        # ESPERADO (ground-truth): repasse congelado das operações confirmadas com repasse.
        batches = list(
            (await s.execute(select(ReceivableAdvanceBatch).where(ReceivableAdvanceBatch.status.in_(CONFIRMED_BATCH_STATUSES)))).scalars().all()
        )
        with_repasse = [b for b in batches if b.repasse_enabled and m(b.repasse_amount) > 0]
        exp_total = Decimal("0.00")
        exp_inst, exp_comp = defaultdict(Decimal), defaultdict(Decimal)
        for b in with_repasse:
            r = m(b.repasse_amount)
            exp_total += r
            exp_inst[inst_name(b.institution_id)] += r
            exp_comp[b.receive_date.replace(day=1)] += r

        # DEPOIS: créditos de OPERATION no Ledger (ativos).
        led = list((await s.execute(select(AdvanceRepasseLedgerEntry))).scalars().all())
        led_op = [e for e in led if e.source_type == RepasseLedgerSource.OPERATION and e.direction == RepasseLedgerDirection.CREDIT and e.reversed_at is None]
        led_total = Decimal("0.00")
        led_inst, led_comp = defaultdict(Decimal), defaultdict(Decimal)
        for e in led_op:
            r = m(e.amount)
            led_total += r
            led_inst[insts[e.institution_id].name if e.institution_id in insts else str(e.institution_id)] += r
            led_comp[e.occurred_at.replace(day=1)] += r

        # RESÍDUO no CAP: linhas de repasse que sobraram (esperado: só as pagas, preservadas).
        cap_rows = [
            r for r in (await s.execute(select(PayableSnapshot).where(PayableSnapshot.type == PayableSnapshotType.ANTECIPACAO_OPERACAO))).scalars().all()
            if "Repasse" in (r.name or "")
        ]
        cap_total = m(sum((m(r.amount_final) for r in cap_rows), Decimal("0")))
        cap_paid = m(sum((m(r.amount_paid) for r in cap_rows if m(r.amount_paid) > 0), Decimal("0")))
        cap_unpaid = m(sum((m(r.amount_final) for r in cap_rows if m(r.amount_paid) == 0), Decimal("0")))

        # ADJUSTMENT (compensação do repasse já pago).
        adj_total = m(sum((m(e.amount) for e in led if e.source_type == RepasseLedgerSource.ADJUSTMENT and e.reversed_at is None), Decimal("0")))

        print("=" * 72)
        print("NEUTRALIDADE FASE 1B — Repasse: CAP → Ledger (read-only)")
        print("=" * 72)
        print(f"\nOperações confirmadas com repasse: {len(with_repasse)}")
        print(f"ESPERADO (Σ repasse_amount) ............ {exp_total}")
        print(f"DEPOIS   (Σ Ledger CREDIT OPERATION) ... {led_total}")
        print(f"DIFERENÇA (Ledger − esperado) .......... {m(led_total - exp_total)}")
        print("\nPor instituição (esperado vs Ledger):")
        for k in sorted(set(exp_inst) | set(led_inst)):
            print(f"   {k:<28} esperado={exp_inst.get(k, Decimal('0.00'))}  ledger={led_inst.get(k, Decimal('0.00'))}  diff={m(led_inst.get(k, Decimal('0')) - exp_inst.get(k, Decimal('0')))}")
        print("\nPor competência (esperado vs Ledger):")
        for k in sorted(set(exp_comp) | set(led_comp)):
            print(f"   {k}  esperado={exp_comp.get(k, Decimal('0.00'))}  ledger={led_comp.get(k, Decimal('0.00'))}  diff={m(led_comp.get(k, Decimal('0')) - exp_comp.get(k, Decimal('0')))}")

        print("\nCAP (resíduo de repasse):")
        print(f"   linhas: {len(cap_rows)} | total={cap_total} | pago(preservado)={cap_paid} | NÃO pago(deve ser 0)={cap_unpaid}")
        print(f"   ADJUSTMENT no Ledger (compensa o pago) = {adj_total}")

        # Critérios de aprovação.
        checks = {
            "Ledger == esperado (total)": m(led_total - exp_total) == 0,
            "Ledger == esperado (por instituição)": all(
                m(led_inst.get(k, Decimal("0")) - exp_inst.get(k, Decimal("0"))) == 0 for k in set(exp_inst) | set(led_inst)
            ),
            "Ledger == esperado (por competência)": all(
                m(led_comp.get(k, Decimal("0")) - exp_comp.get(k, Decimal("0"))) == 0 for k in set(exp_comp) | set(led_comp)
            ),
            "CAP sem repasse NÃO pago (resíduo=0)": cap_unpaid == 0,
            "Repasse pago preservado == ADJUSTMENT": cap_paid == adj_total,
        }
        print("\nCritérios:")
        for name, ok in checks.items():
            print(f"   [{'OK' if ok else 'FALHA'}] {name}")
        approved = all(checks.values())
        print("\nRESULTADO:", "APROVADO — neutralidade confirmada (diferença zero)." if approved else "REPROVADO — ver diferenças acima.")
        return 0 if approved else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
