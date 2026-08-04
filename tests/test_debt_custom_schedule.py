"""Cronograma Financeiro Personalizado (Endividamento — Modo 2). Fase 2: geração do CAP.

Valida as decisões arquiteturais:
- cada parcela do cronograma gera 1 título no CAP com valor/vencimento EXATOS;
- competência SEM parcela nunca gera título (reconciliador não inventa referência);
- Modo 1 (parcelas iguais / obrigatório mensal) permanece inalterado;
- fechamento (Σ cronograma == renegociado) bloqueia salvar;
- parcela PAGA é imutável (histórico preservado).

Testes de banco NÃO commitam (rollback ao final) — não alteram dados reais. Usam mês 2099
isolado para não colidir com dados restaurados de produção no ambiente de teste.
"""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from uuid import uuid4


def _debt_item(tag: str, *, uses_schedule: bool, renegotiated: float, is_monthly_required: bool = False):
    from app.models.company_finance import CompanyFinancialItem, RenegotiationType

    return CompanyFinancialItem(
        tipo="endividamento",
        nome=f"Acordo cronograma {tag}",
        valor_referencia=renegotiated,
        is_active=True,
        start_date=date(2099, 1, 1),
        end_date=None,
        cost_center="Financeiro",
        cost_center_system="FINANCEIRO",
        has_renegotiation=True,
        renegotiated_amount=renegotiated,
        renegotiation_type=RenegotiationType.INSTALLMENTS,
        installment_count=None if uses_schedule else 3,
        installment_value=None if uses_schedule else round(renegotiated / 3, 2),
        is_monthly_required=is_monthly_required,
        uses_custom_schedule=uses_schedule,
    )


class DebtCustomScheduleTests(unittest.IsolatedAsyncioTestCase):
    async def _prelude(self, session):
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        try:
            await session.execute(text("SELECT uses_custom_schedule FROM company_financial_items LIMIT 1"))
            await session.execute(text("SELECT schedule_seq FROM company_financial_payments LIMIT 1"))
        except ProgrammingError:
            self.skipTest("Colunas do cronograma ausentes (rode alembic upgrade head).")

    async def _title(self, session, item_id, comp):
        from sqlalchemy import select
        from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType

        return (
            await session.execute(
                select(PayableSnapshot).where(
                    PayableSnapshot.ref_id == item_id,
                    PayableSnapshot.month == comp,
                    PayableSnapshot.type == PayableSnapshotType.ENDIVIDAMENTO,
                )
            )
        ).scalars().all()

    async def test_schedule_generates_exact_titles_and_stops_after_end(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.company_finance_service import CompanyFinanceService
        from app.services.payable_snapshot_service import PayableSnapshotService

        await engine.dispose()
        tag = uuid4().hex[:6]
        async with AsyncSessionLocal() as session:
            await self._prelude(session)
            try:
                item = _debt_item(tag, uses_schedule=True, renegotiated=6000.0)
                session.add(item)
                await session.flush()

                cf = CompanyFinanceService(session)
                await cf.replace_schedule(
                    item_id=item.id,
                    lines=[
                        {"seq": 1, "vencimento": date(2099, 5, 20), "valor": 1000.0, "descricao": "Parcela 1"},
                        {"seq": 2, "vencimento": date(2099, 6, 20), "valor": 2000.0, "descricao": "Parcela 2"},
                        {"seq": 3, "vencimento": date(2099, 7, 20), "valor": 3000.0, "descricao": "Parcela 3"},
                    ],
                )
                svc = PayableSnapshotService(session)

                # Cada competência com parcela gera EXATAMENTE 1 título com valor/vencimento exatos.
                expected = {
                    date(2099, 5, 1): (1000.0, date(2099, 5, 20)),
                    date(2099, 6, 1): (2000.0, date(2099, 6, 20)),
                    date(2099, 7, 1): (3000.0, date(2099, 7, 20)),
                }
                for comp, (valor, venc) in expected.items():
                    await svc._generate_company_finance_payables(payment_month=comp)
                    await session.flush()
                    rows = await self._title(session, item.id, comp)
                    self.assertEqual(len(rows), 1, f"esperado 1 título em {comp}")
                    self.assertEqual(float(rows[0].amount_final), valor)
                    self.assertEqual(rows[0].due_date, venc)

                # Competência APÓS o fim do cronograma NÃO gera nada (sem referência inventada).
                for comp in (date(2099, 8, 1), date(2099, 9, 1)):
                    await svc._generate_company_finance_payables(payment_month=comp)
                    await session.flush()
                    self.assertEqual(await self._title(session, item.id, comp), [], f"{comp} não deveria gerar título")
            finally:
                await session.rollback()

    async def test_legacy_installments_still_materialize_reference(self) -> None:
        """Modo 1 (parcelas iguais + obrigatório mensal) permanece gerando a referência."""
        from app.database.session import AsyncSessionLocal, engine
        from app.services.payable_snapshot_service import PayableSnapshotService

        await engine.dispose()
        tag = uuid4().hex[:6]
        comp = date(2099, 5, 1)
        async with AsyncSessionLocal() as session:
            await self._prelude(session)
            try:
                item = _debt_item(tag, uses_schedule=False, renegotiated=9000.0, is_monthly_required=True)
                session.add(item)
                await session.flush()

                await PayableSnapshotService(session)._generate_company_finance_payables(payment_month=comp)
                await session.flush()
                rows = await self._title(session, item.id, comp)
                self.assertEqual(len(rows), 1)
                self.assertEqual(float(rows[0].amount_final), 3000.0)  # installment_value = 9000/3
            finally:
                await session.rollback()

    async def test_closure_blocks_unbalanced_schedule(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.company_finance_service import CompanyFinanceService

        await engine.dispose()
        tag = uuid4().hex[:6]
        async with AsyncSessionLocal() as session:
            await self._prelude(session)
            try:
                item = _debt_item(tag, uses_schedule=True, renegotiated=5000.0)
                session.add(item)
                await session.flush()
                cf = CompanyFinanceService(session)

                # Σ cronograma (4000) != renegociado (5000) → bloqueia.
                with self.assertRaises(ValueError):
                    await cf.replace_schedule(
                        item_id=item.id,
                        lines=[
                            {"seq": 1, "vencimento": date(2099, 5, 20), "valor": 2000.0},
                            {"seq": 2, "vencimento": date(2099, 6, 20), "valor": 2000.0},
                        ],
                    )
                # allow_unbalanced=True → permite salvar mesmo com diferença.
                item2 = await cf.replace_schedule(
                    item_id=item.id,
                    lines=[
                        {"seq": 1, "vencimento": date(2099, 5, 20), "valor": 2000.0},
                        {"seq": 2, "vencimento": date(2099, 6, 20), "valor": 2000.0},
                    ],
                    allow_unbalanced=True,
                )
                self.assertIsNotNone(item2)
                self.assertFalse(cf.last_payable_sync["closure"]["is_valid"])
                self.assertEqual(cf.last_payable_sync["closure"]["diferenca"], 1000.0)
            finally:
                await session.rollback()

    async def test_paid_installment_is_immutable(self) -> None:
        from sqlalchemy import select
        from app.database.session import AsyncSessionLocal, engine
        from app.models.company_finance import CompanyFinancialPayment
        from app.services.company_finance_service import CompanyFinanceService
        from app.services.payable_snapshot_service import PayableSnapshotService

        await engine.dispose()
        tag = uuid4().hex[:6]
        async with AsyncSessionLocal() as session:
            await self._prelude(session)
            try:
                item = _debt_item(tag, uses_schedule=True, renegotiated=2000.0)
                session.add(item)
                await session.flush()
                cf = CompanyFinanceService(session)
                await cf.replace_schedule(
                    item_id=item.id,
                    lines=[
                        {"seq": 1, "vencimento": date(2099, 5, 20), "valor": 1000.0},
                        {"seq": 2, "vencimento": date(2099, 6, 20), "valor": 1000.0},
                    ],
                )
                # Gera o título da parcela 1 e simula pagamento.
                await PayableSnapshotService(session)._generate_company_finance_payables(payment_month=date(2099, 5, 1))
                await session.flush()
                title = (await self._title(session, item.id, date(2099, 5, 1)))[0]
                title.amount_paid = Decimal("1000.00")
                await session.flush()

                # Tenta mudar o vencimento da parcela PAGA (mantendo o total fechado).
                await cf.replace_schedule(
                    item_id=item.id,
                    lines=[
                        {"seq": 1, "vencimento": date(2099, 5, 25), "valor": 1000.0},  # paga: deve ser preservada
                        {"seq": 2, "vencimento": date(2099, 6, 20), "valor": 1000.0},
                    ],
                )
                # Parcela paga permanece intacta e o aviso reporta a preservação.
                seq1 = (
                    await session.execute(
                        select(CompanyFinancialPayment).where(
                            CompanyFinancialPayment.item_id == item.id,
                            CompanyFinancialPayment.schedule_seq == 1,
                        )
                    )
                ).scalars().one()
                self.assertEqual(seq1.due_date, date(2099, 5, 20))  # NÃO mudou
                self.assertTrue(cf.last_payable_sync["skipped_paid"])  # reportado
            finally:
                await session.rollback()

    async def test_reading_derives_from_cap_payments_not_planned_lines(self) -> None:
        """Fonte ÚNICA: pago/saldo/progresso vêm do CAP (pagamento real), nunca das linhas planejadas."""
        from app.database.session import AsyncSessionLocal, engine
        from app.services.company_finance_service import CompanyFinanceService
        from app.services.payable_snapshot_service import PayableSnapshotService

        await engine.dispose()
        tag = uuid4().hex[:6]
        async with AsyncSessionLocal() as session:
            await self._prelude(session)
            try:
                item = _debt_item(tag, uses_schedule=True, renegotiated=6000.0)
                session.add(item)
                await session.flush()
                cf = CompanyFinanceService(session)
                await cf.replace_schedule(
                    item_id=item.id,
                    lines=[
                        {"seq": 1, "vencimento": date(2099, 5, 20), "valor": 1000.0},
                        {"seq": 2, "vencimento": date(2099, 6, 20), "valor": 2000.0},
                        {"seq": 3, "vencimento": date(2099, 7, 20), "valor": 3000.0},
                    ],
                )
                svc = PayableSnapshotService(session)
                await svc._generate_company_finance_payables(payment_month=date(2099, 5, 1))
                await session.flush()
                title = (await self._title(session, item.id, date(2099, 5, 1)))[0]
                # Pago REAL do CAP na parcela 1 (amount_paid). Mês 2099 impede register_payment
                # (data futura), então setamos amount_paid direto — mesma fonte que _cap_paid_by_entry.
                from decimal import Decimal as _D

                title.amount_paid = _D("1000.00")
                await session.flush()

                rows = await cf.list_items("endividamento", "2099-05")
                row = next(r for r in rows if r["id"] == item.id)
                # Contrato de leitura expõe o modo (o frontend decide a UI por este flag).
                self.assertTrue(row["uses_custom_schedule"])
                # "Pago" = CAP (1000), NUNCA a soma planejada (6000).
                self.assertEqual(row["total_pago"], 1000.0)
                self.assertEqual(row["restante"], 5000.0)
                self.assertAlmostEqual(row["progresso"], 1000.0 / 6000.0, places=4)
                sch = row["schedule"]
                self.assertIsNotNone(sch)
                self.assertEqual(sch["parcelas_total"], 3)
                self.assertEqual(sch["parcelas_pagas"], 1)
                self.assertEqual(sch["parcelas_restantes"], 2)
                self.assertEqual(sch["total_pago"], 1000.0)
                self.assertEqual(sch["saldo_restante"], 5000.0)
                self.assertEqual(sch["proxima_vencimento"], date(2099, 6, 20))
                self.assertEqual(sch["proxima_valor"], 2000.0)
                self.assertEqual(sch["ultima_vencimento"], date(2099, 7, 20))
                self.assertEqual(sch["data_encerramento"], date(2099, 7, 20))

                # Pendências: a parcela de 2099-06 (não paga) é pendência; a de 2099-05 (paga) não.
                pend_06 = await cf.pendencias("endividamento", "2099-06")
                self.assertTrue(any(p["item_id"] == item.id for p in pend_06["pendencias"]))
                pend_05 = await cf.pendencias("endividamento", "2099-05")
                self.assertFalse(any(p["item_id"] == item.id for p in pend_05["pendencias"]))
                # Contrato do ROUTER: a resposta precisa validar no schema (origem="cronograma"
                # deve ser aceita) — regressão do 500 em produção.
                from app.schemas.company_finance import PendenciasCustosFixosRead

                self.assertEqual(
                    "cronograma",
                    next(p["origem"] for p in pend_06["pendencias"] if p["item_id"] == item.id),
                )
                PendenciasCustosFixosRead.model_validate(pend_06)
            finally:
                await session.rollback()

    async def test_legacy_debt_reading_unchanged(self) -> None:
        """Modo 1: leitura permanece derivando total_pago da grade (it.payments) e schedule=None."""
        from app.database.session import AsyncSessionLocal, engine
        from app.models.company_finance import CompanyFinancialPayment
        from app.services.company_finance_service import CompanyFinanceService

        await engine.dispose()
        tag = uuid4().hex[:6]
        async with AsyncSessionLocal() as session:
            await self._prelude(session)
            try:
                item = _debt_item(tag, uses_schedule=False, renegotiated=9000.0)
                session.add(item)
                await session.flush()
                session.add(
                    CompanyFinancialPayment(
                        item_id=item.id, competencia=date(2099, 5, 1), valor=3000.0, due_date=date(2099, 5, 20)
                    )
                )
                await session.flush()

                cf = CompanyFinanceService(session)
                rows = await cf.list_items("endividamento", "2099-05")
                row = next(r for r in rows if r["id"] == item.id)
                self.assertEqual(row["total_pago"], 3000.0)  # soma da grade (comportamento legado)
                self.assertIsNone(row["schedule"])  # sem contrato de cronograma
            finally:
                await session.rollback()

    async def test_schedule_mode_blocks_grade_and_modal(self) -> None:
        """Modo 2: grade mensal e modal de competência ficam read-only (edição só via cronograma)."""
        from app.database.session import AsyncSessionLocal, engine
        from app.services.company_finance_service import CompanyFinanceService

        await engine.dispose()
        tag = uuid4().hex[:6]
        async with AsyncSessionLocal() as session:
            await self._prelude(session)
            try:
                item = _debt_item(tag, uses_schedule=True, renegotiated=1000.0)
                session.add(item)
                await session.flush()
                cf = CompanyFinanceService(session)
                await cf.replace_schedule(
                    item_id=item.id,
                    lines=[{"seq": 1, "vencimento": date(2099, 5, 20), "valor": 1000.0}],
                )
                with self.assertRaises(ValueError):
                    await cf.replace_payments(item_id=item.id, pagamentos=[{"mes": "2099-05", "valor": 100.0}])
                with self.assertRaises(ValueError):
                    await cf.replace_entries(
                        item_id=item.id, competencia="2099-05", lancamentos=[{"valor": 100.0}]
                    )
            finally:
                await session.rollback()

    def test_preview_ranges_expands_movida_like_agreement(self) -> None:
        from app.services.company_finance_service import CompanyFinanceService

        out = CompanyFinanceService.preview_ranges(
            [
                {"seq_start": 1, "seq_end": 6, "valor": 15000, "dia": 20, "primeiro_vencimento": "2026-08-01"},
                {"seq_start": 7, "seq_end": 12, "valor": 20000, "dia": 20, "primeiro_vencimento": "2027-02-01"},
                {"seq_start": 13, "seq_end": 30, "valor": 45000, "dia": 20, "primeiro_vencimento": "2027-08-01"},
            ]
        )
        self.assertEqual(out["count"], 30)
        self.assertEqual(out["lines"][0]["vencimento"], date(2026, 8, 20))
        self.assertEqual(out["lines"][-1]["vencimento"], date(2029, 1, 20))
        self.assertEqual(out["total"], 15000 * 6 + 20000 * 6 + 45000 * 18)
