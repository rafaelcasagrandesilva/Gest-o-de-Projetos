"""Custos Fixos — MÚLTIPLOS LANÇAMENTOS por competência (Fases 2–4).

Valida, de forma GENÉRICA (qualquer fornecedor; sem regra específica):
- 1 lançamento → comportamento idêntico ao anterior (1 título = referência/valor);
- N lançamentos → N títulos independentes no CAP, consolidados (soma) na grade;
- descrição do lançamento vira o SUBTÍTULO do título (item_description) e a coluna
  Observações do relatório; editar o cadastro NÃO apaga a descrição por lançamento;
- exclusão/edição/pagamento por lançamento preservam os demais e o histórico;
- Σ(CAP) == Σ(Relatório). Testes de banco NÃO commitam (rollback ao final).
"""

from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError


def _fixed_item(tag: str):
    from app.models.company_finance import CompanyFinancialItem

    return CompanyFinancialItem(
        tipo="custo_fixo",
        nome=f"Fornecedor multi {tag}",
        valor_referencia=Decimal("1000.00"),
        is_active=True,
        start_date=date(2019, 1, 1),
        cost_center="Administrativo",
        cost_center_system="ADMINISTRATIVO",
    )


class FixedCostMultiEntriesTests(unittest.IsolatedAsyncioTestCase):
    async def _prelude(self, session, comp: date) -> None:
        from app.models.payable_snapshot_generation import PayableSnapshotGeneration
        from app.services.payable_snapshot_service import PayableSnapshotService

        try:
            await session.execute(text("SELECT entry_id FROM payable_snapshots LIMIT 1"))
            await session.execute(text("SELECT descricao FROM company_financial_payments LIMIT 1"))
        except ProgrammingError:
            self.skipTest("Colunas ausentes (rode alembic upgrade head).")
        if not await PayableSnapshotService(session).is_generated(month=comp):
            session.add(PayableSnapshotGeneration(month=comp, created_at=datetime.now(timezone.utc)))
        await session.flush()

    async def _cap_lines(self, session, item_id, comp):
        from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType

        return list(
            (
                await session.execute(
                    select(PayableSnapshot).where(
                        PayableSnapshot.ref_id == item_id,
                        PayableSnapshot.month == comp,
                        PayableSnapshot.type == PayableSnapshotType.FIXED_COST,
                    )
                )
            )
            .scalars()
            .all()
        )

    async def test_single_entry_matches_prior_behavior(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.company_finance_service import CompanyFinanceService

        await engine.dispose()
        comp, COMP = date(2099, 5, 1), "2099-05"
        async with AsyncSessionLocal() as s:
            await self._prelude(s, comp)
            try:
                item = _fixed_item(uuid4().hex[:6])
                s.add(item)
                await s.flush()
                svc = CompanyFinanceService(s)
                await svc.replace_entries(
                    item_id=item.id, competencia=COMP,
                    lancamentos=[{"valor": 1000.0, "vencimento": "2099-05-10", "descricao": None}],
                )
                lines = await self._cap_lines(s, item.id, comp)
                self.assertEqual(len(lines), 1)
                self.assertEqual(float(lines[0].amount_final), 1000.0)
                # Grade consolidada: um único mês somado, count=1.
                await s.refresh(item, attribute_names=["payments"])
                read = await svc._item_to_read(item, comp)
                pm = next(p for p in read["pagamentos"] if p["mes"] == COMP)
                self.assertEqual(pm["valor"], 1000.0)
                self.assertEqual(pm["count"], 1)
                self.assertEqual(read["pago_mes"], 1000.0)
            finally:
                await s.rollback()

    async def test_multiple_entries_individual_in_cap_consolidated_in_grid(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.company_finance_service import CompanyFinanceService
        from app.services.operational_report_service import OperationalReportService

        await engine.dispose()
        comp, COMP = date(2099, 8, 1), "2099-08"
        async with AsyncSessionLocal() as s:
            await self._prelude(s, comp)
            try:
                item = _fixed_item(uuid4().hex[:6])
                s.add(item)
                await s.flush()
                svc = CompanyFinanceService(s)
                await svc.replace_entries(
                    item_id=item.id, competencia=COMP,
                    lancamentos=[
                        {"valor": 2000.0, "vencimento": "2099-08-15", "descricao": "1ª Quinzena"},
                        {"valor": 1450.0, "vencimento": "2099-08-31", "descricao": "2ª Quinzena"},
                        {"valor": 500.0, "vencimento": "2099-08-31", "descricao": "Juros"},
                    ],
                )
                lines = await self._cap_lines(s, item.id, comp)
                # N títulos independentes, cada um com sua descrição (subtítulo).
                self.assertEqual(len(lines), 3)
                self.assertEqual(
                    {l.item_description for l in lines}, {"1ª Quinzena", "2ª Quinzena", "Juros"}
                )
                # Consolidado na grade: 1 linha de mês, soma, count=3.
                await s.refresh(item, attribute_names=["payments"])
                read = await svc._item_to_read(item, comp)
                pm = next(p for p in read["pagamentos"] if p["mes"] == COMP)
                self.assertEqual(pm["valor"], 3950.0)
                self.assertEqual(pm["count"], 3)
                # Σ(CAP) == Σ(Relatório) e Observações = descrição.
                rep = await OperationalReportService(s).generate_payables_detailed(
                    filters={"month": COMP}, accessible_project_ids=None, sees_all_projects=True
                )
                mine = [r for r in rep["rows"] if r["nome"] == item.nome]
                self.assertEqual(
                    {r["observacoes"] for r in mine}, {"1ª Quinzena", "2ª Quinzena", "Juros"}
                )
                sum_cap = sum(float(l.amount_final) for l in lines)
                sum_rep = sum(r["valor_final"] for r in mine)
                self.assertAlmostEqual(sum_cap, sum_rep, places=2)
                self.assertAlmostEqual(sum_cap, 3950.0, places=2)
            finally:
                await s.rollback()

    async def test_delete_one_pay_one_preserves_others_and_descricao(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.company_finance_service import CompanyFinanceService
        from app.services.payable_snapshot_service import _sync_legacy_paid_fields

        await engine.dispose()
        comp, COMP = date(2099, 8, 1), "2099-08"
        async with AsyncSessionLocal() as s:
            await self._prelude(s, comp)
            try:
                item = _fixed_item(uuid4().hex[:6])
                s.add(item)
                await s.flush()
                svc = CompanyFinanceService(s)
                await svc.replace_entries(
                    item_id=item.id, competencia=COMP,
                    lancamentos=[
                        {"valor": 2000.0, "vencimento": "2099-08-15", "descricao": "1ª Quinzena"},
                        {"valor": 1450.0, "vencimento": "2099-08-31", "descricao": "2ª Quinzena"},
                        {"valor": 500.0, "vencimento": "2099-08-31", "descricao": "Juros"},
                    ],
                )
                lines = await self._cap_lines(s, item.id, comp)
                by_desc = {l.item_description: l for l in lines}
                # Paga a 2ª Quinzena.
                paid = by_desc["2ª Quinzena"]
                paid.amount_paid = paid.amount_final
                _sync_legacy_paid_fields(paid)
                await s.flush()

                # Remove "Juros" (aberto) e tenta remover "2ª Quinzena" (paga → bloqueada).
                await svc.replace_entries(
                    item_id=item.id, competencia=COMP,
                    lancamentos=[
                        {"id": str(by_desc["1ª Quinzena"].entry_id), "valor": 2000.0,
                         "vencimento": "2099-08-15", "descricao": "1ª Quinzena"},
                        {"id": str(by_desc["2ª Quinzena"].entry_id), "valor": 1450.0,
                         "vencimento": "2099-08-31", "descricao": "2ª Quinzena"},
                    ],
                )
                lines2 = await self._cap_lines(s, item.id, comp)
                descs = {l.item_description for l in lines2}
                self.assertEqual(descs, {"1ª Quinzena", "2ª Quinzena"})  # Juros removido
                # Pagamento da 2ª Quinzena preservado.
                paid2 = next(l for l in lines2 if l.item_description == "2ª Quinzena")
                self.assertEqual(float(paid2.amount_paid), 1450.0)

                # Editar o cadastro NÃO apaga as descrições por lançamento.
                await svc.update_item(item_id=item.id, data={"category": "Custos diversos"})
                lines3 = await self._cap_lines(s, item.id, comp)
                self.assertEqual(
                    {l.item_description for l in lines3}, {"1ª Quinzena", "2ª Quinzena"}
                )
            finally:
                await s.rollback()


if __name__ == "__main__":
    unittest.main()
