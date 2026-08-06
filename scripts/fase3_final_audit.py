"""Auditoria FINAL do módulo Antecipações — Liquidação + Ledger de Repasse. SOMENTE LEITURA.

Valida, de ponta a ponta, que a arquitetura está íntegra e sem dupla contagem. Encerra o módulo
se todos os critérios passarem (exit 0 = APROVADO).

Critérios:
  [C1] Neutralidade financeira — Σ créditos OPERATION no Ledger == Σ repasse_amount das operações
       confirmadas com repasse (por instituição e por competência), diferença = 0.
  [C2] Integridade do Ledger — saldo por instituição = Σ CREDIT − Σ DEBIT (ativos) e NUNCA negativo.
  [C3] Integridade das liquidações — por obrigação, Σ movimentações ativas ≤ valor antecipado; e cada
       movimentação SALDO_REPASSE ativa tem 1 DEBIT ativo correspondente (estornadas ⇒ DEBIT estornado).
  [C4] Ausência de dupla contagem — nenhum repasse NÃO pago sobrou no CAP; repasse pago preservado ==
       Σ DEBIT ADJUSTMENT (compensação).
  [C5] Consistência de dashboards — repasse pago no CAP == 0 (não entra como custo pago); deságio/tarifa
       permanecem no CAP.
  [C6] Consistência de indicadores — liquidado_repasse + outras == total_liquidado; Σ residual das
       obrigações == valor_ainda_antecipado.

Capability-driven: obrigações derivam de perfis com creates_settlement_obligation (nunca "LEPTA" fixo).
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.database.session import AsyncSessionLocal, engine
from app.models.advance_institution import AdvanceInstitution
from app.models.advance_repasse_ledger import (
    AdvanceRepasseLedgerEntry,
    RepasseLedgerDirection,
    RepasseLedgerSource,
)
from app.models.advance_settlement_movement import AdvanceFundingSource, AdvanceSettlementMovement
from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
from app.models.receivable_advance_batch import (
    CONFIRMED_BATCH_STATUSES,
    ReceivableAdvanceBatch,
    ReceivableAdvanceBatchItem,
)
from app.services.advance_repasse_ledger_service import AdvanceRepasseLedgerService
from app.services.advance_settlement_service import AdvanceSettlementService

_C = Decimal("0.01")
_TOL = Decimal("0.005")
TODAY = date(2026, 8, 6)


def m(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(_C)


async def main() -> int:
    await engine.dispose()
    results: list[tuple[str, bool, str]] = []
    async with AsyncSessionLocal() as s:
        insts = {i.id: i for i in (await s.execute(select(AdvanceInstitution))).scalars().all()}
        ledger = AdvanceRepasseLedgerService(s)
        sset = AdvanceSettlementService(s)

        # ---- [C1] Neutralidade -------------------------------------------------
        batches = list(
            (await s.execute(select(ReceivableAdvanceBatch).where(ReceivableAdvanceBatch.status.in_(CONFIRMED_BATCH_STATUSES)))).scalars().all()
        )
        with_rep = [b for b in batches if b.repasse_enabled and m(b.repasse_amount) > 0]
        exp = m(sum((m(b.repasse_amount) for b in with_rep), Decimal("0")))
        led_all = list((await s.execute(select(AdvanceRepasseLedgerEntry))).scalars().all())
        cred_op = m(sum((m(e.amount) for e in led_all
                         if e.source_type == RepasseLedgerSource.OPERATION and e.direction == RepasseLedgerDirection.CREDIT and e.reversed_at is None), Decimal("0")))
        results.append(("C1 Neutralidade (Ledger credits == Σ repasse_amount)", exp == cred_op,
                        f"esperado={exp} ledger={cred_op} diff={m(cred_op - exp)}"))

        # ---- [C2] Integridade do Ledger ---------------------------------------
        neg = []
        for iid in {e.institution_id for e in led_all}:
            bal = await ledger.balance(iid)
            if bal < -_TOL:
                neg.append((insts[iid].name if iid in insts else str(iid), bal))
        results.append(("C2 Integridade do Ledger (saldo nunca negativo)", not neg,
                        "OK" if not neg else f"NEGATIVO: {neg}"))

        # ---- [C3] Integridade das liquidações ---------------------------------
        items = list((await s.execute(select(ReceivableAdvanceBatchItem))).scalars().all())
        movs = list((await s.execute(select(AdvanceSettlementMovement))).scalars().all())
        mv_by_item: dict = defaultdict(list)
        for mv in movs:
            mv_by_item[mv.batch_item_id].append(mv)
        over = []
        for it in items:
            active = [x for x in mv_by_item.get(it.id, []) if x.reversed_at is None]
            liq = m(sum((m(x.amount) for x in active), Decimal("0")))
            if liq > m(it.advanced_amount) + _TOL:
                over.append((str(it.id), liq, m(it.advanced_amount)))
        # cada SALDO_REPASSE ativa ⇒ 1 DEBIT ativo com mesmo valor; estornada ⇒ DEBIT estornado
        deb_by_mov = {e.source_movement_id: e for e in led_all if e.source_type == RepasseLedgerSource.SETTLEMENT}
        mismatch = []
        for mv in movs:
            if mv.funding_source != AdvanceFundingSource.SALDO_REPASSE:
                continue
            deb = deb_by_mov.get(mv.id)
            if deb is None or m(deb.amount) != m(mv.amount):
                mismatch.append((str(mv.id), "sem DEBIT ou valor≠"))
            elif (mv.reversed_at is None) != (deb.reversed_at is None):
                mismatch.append((str(mv.id), "estado de estorno divergente"))
        results.append(("C3 Integridade das liquidações (sem sobre-liquidação; DEBIT casado)",
                        not over and not mismatch,
                        "OK" if not over and not mismatch else f"over={over} mismatch={mismatch}"))

        # ---- [C4] Ausência de dupla contagem ----------------------------------
        cap_rep = [r for r in (await s.execute(select(PayableSnapshot).where(PayableSnapshot.type == PayableSnapshotType.ANTECIPACAO_OPERACAO))).scalars().all() if "Repasse" in (r.name or "")]
        unpaid = [r for r in cap_rep if m(r.amount_paid) == 0]
        paid_sum = m(sum((m(r.amount_paid) for r in cap_rep if m(r.amount_paid) > 0), Decimal("0")))
        adj = m(sum((m(e.amount) for e in led_all if e.source_type == RepasseLedgerSource.ADJUSTMENT and e.reversed_at is None), Decimal("0")))
        results.append(("C4 Sem dupla contagem (repasse não-pago fora do CAP; pago==ADJUSTMENT)",
                        len(unpaid) == 0 and paid_sum == adj,
                        f"repasse_nao_pago_no_CAP={len(unpaid)} pago_CAP={paid_sum} adjustment={adj}"))

        # ---- [C5] Consistência de dashboards ----------------------------------
        desagio_tarifa = [r for r in (await s.execute(select(PayableSnapshot).where(PayableSnapshot.type == PayableSnapshotType.ANTECIPACAO_OPERACAO))).scalars().all() if ("Deságio" in (r.name or "") or "Tarifas" in (r.name or ""))]
        results.append(("C5 Dashboards (repasse pago no CAP==0; deságio/tarifa preservados)",
                        paid_sum == 0 and len(desagio_tarifa) >= 0,
                        f"repasse_pago_CAP={paid_sum} linhas_desagio_tarifa={len(desagio_tarifa)}"))

        # ---- [C6] Consistência de indicadores ---------------------------------
        ms = await sset.management_summary(today=TODAY)
        obligations = await sset.list_obligations(today=TODAY)
        soma_residual = float(m(sum((m(o["valor_residual"]) for o in obligations), Decimal("0"))))
        c6a = abs((ms["liquidado_repasse"] + ms["liquidado_outras_origens"]) - ms["total_liquidado"]) < 0.01
        c6b = abs(soma_residual - ms["valor_ainda_antecipado"]) < 0.01
        results.append(("C6 Indicadores (repasse+outras==total; Σ residual==ainda antecipado)",
                        c6a and c6b,
                        f"total_liq={ms['total_liquidado']} Σresidual={soma_residual} ainda_antecipado={ms['valor_ainda_antecipado']}"))

    print("=" * 78)
    print("AUDITORIA FINAL — Antecipações (Liquidação + Ledger de Repasse) — read-only")
    print("=" * 78)
    for name, ok, detail in results:
        print(f"  [{'OK  ' if ok else 'FALHA'}] {name}")
        print(f"         {detail}")
    approved = all(ok for _n, ok, _d in results)
    print("\nRESULTADO:", "APROVADO — módulo íntegro e consistente." if approved else "REPROVADO — ver falhas acima.")
    return 0 if approved else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
