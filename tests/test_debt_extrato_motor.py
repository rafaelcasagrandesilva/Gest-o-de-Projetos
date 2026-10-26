"""Extrato Analítico do Endividamento × motor de saldo.

Regressão: o Extrato fazia `valor de origem − pago` e mostrava QUITADA (acima de 100%) uma
dívida que, com aportes e juros, ainda tinha saldo. Agora a linha do razão
traz `debt_total` (valor de hoje, com aportes e encargos) e `total_pago_realizado`, e fecha:
valor − pago = saldo = saldo de hoje do modal "Evolução da dívida".

Testes de banco NÃO commitam (rollback ao final).
"""

from __future__ import annotations

import unittest
from datetime import date
from uuid import uuid4


def _month(offset: int) -> date:
    t = date.today()
    idx = t.year * 12 + (t.month - 1) + offset
    return date(idx // 12, idx % 12 + 1, 1)


def _item(tag: str, *, valor: float, renegotiated: float | None = None):
    from app.models.company_finance import CompanyFinancialItem

    return CompanyFinancialItem(
        tipo="endividamento",
        nome=f"Extrato motor {tag}",
        valor_referencia=valor,
        is_active=True,
        start_date=_month(-6),
        cost_center="Financeiro",
        cost_center_system="FINANCEIRO",
        has_renegotiation=renegotiated is not None,
        renegotiated_amount=renegotiated,
        uses_custom_schedule=False,
    )


class DebtExtratoMotorTests(unittest.IsolatedAsyncioTestCase):
    async def _row_and_ledger(self, session, item_id):
        from app.services.company_finance_service import CompanyFinanceService
        from app.services.debt_ledger_service import DebtLedgerService

        session.expire_all()
        rows = await CompanyFinanceService(session).list_items("endividamento", None)
        row = next(r for r in rows if r["id"] == item_id)
        ledger = await DebtLedgerService(session).ledger(item_id=item_id)
        return row, ledger

    async def test_debt_with_interest_is_not_settled_by_paying_the_origin(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.models.company_finance import (
            CompanyFinancialEvent,
            CompanyFinancialPayment,
            CompanyFinancialRate,
        )

        await engine.dispose()
        async with AsyncSessionLocal() as session:
            try:
                item = _item(uuid4().hex[:6], valor=10000.0)
                session.add(item)
                await session.flush()
                session.add(CompanyFinancialRate(item_id=item.id, valid_from=_month(-6), monthly_rate=0.03))
                session.add(CompanyFinancialEvent(item_id=item.id, competencia=_month(-3), kind="APORTE", amount=8000.0))
                # Pago realizado (11 mil) passa do valor de origem (10 mil) — antes = QUITADA.
                for off, v in ((-5, 5000.0), (-4, 6000.0)):
                    session.add(CompanyFinancialPayment(item_id=item.id, competencia=_month(off), valor=v))
                # Lançamento futuro é plano: fica fora do pago e do saldo.
                session.add(CompanyFinancialPayment(item_id=item.id, competencia=_month(2), valor=999.0))
                await session.flush()

                row, ledger = await self._row_and_ledger(session, item.id)
                saldo_hoje = ledger["resumo"]["saldo_atual"]

                self.assertGreater(saldo_hoje, 0)
                self.assertAlmostEqual(row["restante"], saldo_hoje, places=2)
                self.assertEqual(row["status"], "ativo")
                self.assertLess(row["progresso"], 1.0)
                self.assertIsNone(row["quitado_em"])
                self.assertEqual(row["total_pago_realizado"], 11000.0)
                # Contrato antigo do cartão preservado: total_pago ainda soma o futuro.
                self.assertEqual(row["total_pago"], 11999.0)
                # A linha do Extrato fecha: valor − pago = saldo; valor inclui aporte e juros.
                self.assertAlmostEqual(row["debt_total"] - row["total_pago_realizado"], row["restante"], places=2)
                self.assertGreater(row["debt_total"], 18000.0)
            finally:
                await session.rollback()

    async def test_renegotiated_base_is_the_ledger_principal(self) -> None:
        """Cadastro zerado com renegociação válida: o razão não pode começar em zero."""
        from app.database.session import AsyncSessionLocal, engine
        from app.models.company_finance import CompanyFinancialPayment, CompanyFinancialRate

        await engine.dispose()
        async with AsyncSessionLocal() as session:
            try:
                item = _item(uuid4().hex[:6], valor=0.0, renegotiated=25882.56)
                session.add(item)
                await session.flush()
                session.add(CompanyFinancialRate(item_id=item.id, valid_from=_month(-6), monthly_rate=0))
                session.add(CompanyFinancialPayment(item_id=item.id, competencia=_month(-1), valor=718.96))
                await session.flush()

                row, ledger = await self._row_and_ledger(session, item.id)

                self.assertEqual(ledger["resumo"]["principal"], 25882.56)
                self.assertAlmostEqual(row["restante"], 25163.60, places=2)
                self.assertEqual(row["debt_total"], 25882.56)
                self.assertEqual(row["status"], "ativo")
            finally:
                await session.rollback()

    async def test_chart_balance_follows_the_ledger_month_by_month(self) -> None:
        """Gráfico "Evolução do saldo restante": cada mês = saldo final do razão (com juros);
        antes do início a dívida não existe. Medido pela diferença que o item faz na série."""
        from app.database.session import AsyncSessionLocal, engine
        from app.models.company_finance import CompanyFinancialPayment, CompanyFinancialRate
        from app.services.company_finance_service import CompanyFinanceService

        def key(d: date) -> str:
            return f"{d.year:04d}-{d.month:02d}"

        inicio, fim = _month(-8), _month(1)
        await engine.dispose()
        async with AsyncSessionLocal() as session:
            try:
                cf = CompanyFinanceService(session)
                antes = {p["mes"]: p["saldo_restante_total"] for p in await cf.chart_series("endividamento", key(inicio), key(fim))}

                item = _item(uuid4().hex[:6], valor=10000.0)
                session.add(item)
                await session.flush()
                session.add(CompanyFinancialRate(item_id=item.id, valid_from=_month(-6), monthly_rate=0.03))
                session.add(CompanyFinancialPayment(item_id=item.id, competencia=_month(-4), valor=10500.0))
                await session.flush()

                _row, ledger = await self._row_and_ledger(session, item.id)
                por_mes = {key(ln["competencia"]): ln["saldo_final"] for ln in ledger["linhas"]}
                depois = {p["mes"]: p["saldo_restante_total"] for p in await cf.chart_series("endividamento", key(inicio), key(fim))}
                delta = {m: round(depois[m] - antes[m], 2) for m in depois}

                self.assertEqual(delta[key(_month(-7))], 0.0)  # antes do início
                self.assertAlmostEqual(delta[key(_month(-6))], 10300.0, places=2)  # 10 mil + 3%
                # Pagou 10,5 mil (mais que a origem) e ainda deve: o gráfico antigo zerava aqui.
                self.assertGreater(delta[key(_month(-4))], 0.0)
                for off in (-4, 0):
                    self.assertAlmostEqual(delta[key(_month(off))], por_mes[key(_month(off))], places=2)
            finally:
                await session.rollback()

    async def test_overpaid_debt_never_shows_negative_balance(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.models.company_finance import CompanyFinancialPayment, CompanyFinancialRate

        await engine.dispose()
        async with AsyncSessionLocal() as session:
            try:
                item = _item(uuid4().hex[:6], valor=1000.0)
                session.add(item)
                await session.flush()
                session.add(CompanyFinancialRate(item_id=item.id, valid_from=_month(-6), monthly_rate=0))
                session.add(CompanyFinancialPayment(item_id=item.id, competencia=_month(-2), valor=3000.0))
                await session.flush()

                row, _ = await self._row_and_ledger(session, item.id)

                self.assertEqual(row["restante"], 0.0)
                self.assertEqual(row["status"], "quitado")
                self.assertEqual(row["progresso"], 1.0)
                # Mês em que zerou: a lista padrão o esconde a partir do seguinte.
                self.assertEqual(row["quitado_em"], _month(-2))
            finally:
                await session.rollback()


class SettledMonthTests(unittest.TestCase):
    def test_ledger_settles_on_the_last_zeroing(self) -> None:
        from decimal import Decimal

        from app.services.company_finance_service import _ledger_settled_month
        from app.services.debt_accrual import LedgerEvent, build_ledger

        # Zera em 03, recebe aporte em 04 e zera de novo em 05: quitada em 05.
        linhas = build_ledger(
            principal=Decimal("1000"),
            origin_month=date(2026, 1, 1),
            through=date(2026, 8, 1),
            events=[LedgerEvent(competencia=date(2026, 4, 1), kind="APORTE", amount=Decimal("500"))],
            payments={date(2026, 3, 1): 1000, date(2026, 5, 1): 500},
            realized_through=date(2026, 6, 1),
        )
        self.assertEqual(_ledger_settled_month(linhas), date(2026, 5, 1))

    def test_ledger_with_balance_is_not_settled(self) -> None:
        from decimal import Decimal

        from app.services.company_finance_service import _ledger_settled_month
        from app.services.debt_accrual import build_ledger

        # Pagamento futuro (projeção) não quita.
        linhas = build_ledger(
            principal=Decimal("1000"),
            origin_month=date(2026, 1, 1),
            through=date(2026, 4, 1),
            payments={date(2026, 4, 1): 1000},
            realized_through=date(2026, 3, 1),
        )
        self.assertIsNone(_ledger_settled_month(linhas))

    def test_schedule_settles_when_paid_reaches_total(self) -> None:
        from app.services.company_finance_service import _schedule_settled_month

        pagos = {date(2026, 3, 1): 1000.0, date(2026, 1, 1): 1000.0, date(2026, 2, 1): 0.0}
        self.assertEqual(_schedule_settled_month(pagos, 2000.0), date(2026, 3, 1))
        # Centavos de diferença: vale o último mês com pagamento.
        self.assertEqual(_schedule_settled_month(pagos, 2000.02), date(2026, 3, 1))


if __name__ == "__main__":
    unittest.main()
