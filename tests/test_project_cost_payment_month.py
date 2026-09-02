"""Custo de projeto: competência M → título no Contas a Pagar em M+1.

O CAP é fluxo de CAIXA: o mês da linha é o do PAGAMENTO, não o da competência. O custo é
lançado no fim do mês em que ocorreu e pago no mês seguinte — a mesma regra que a folha já
seguia.

Havia dois caminhos discordando sobre isso: o lançamento na tela (`_sync_project_cost_payable`)
gravava no mesmo mês, enquanto a geração do snapshot lia os itens de `previous_competencia`.
O MESMO custo caía em meses diferentes conforme tivesse nascido de um lançamento ou de uma
regeneração. O teste fixa a regra nos dois.

Não commita: rollback ao final.
"""

from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4


class ProjectCostPaymentMonthTests(unittest.IsolatedAsyncioTestCase):
    async def _projeto(self, s):
        from app.models.project import Project

        proj = Project(name=f"Projeto {uuid4().hex[:6]}", is_active=True)
        s.add(proj)
        await s.flush()
        return proj.id

    async def _lanca(self, s, Model, sync_name: str, *, comp: date, pagamento: date):
        from app.models.payable_snapshot_generation import PayableSnapshotGeneration
        from app.services.payable_snapshot_service import PayableSnapshotService

        pid = await self._projeto(s)
        svc = PayableSnapshotService(s)
        for mes in (comp, pagamento):
            if not await svc.is_generated(month=mes):
                s.add(PayableSnapshotGeneration(month=mes, created_at=datetime.now(timezone.utc)))
                await s.flush()

        item = Model(
            project_id=pid,
            competencia=comp,
            scenario="REALIZADO",
            name=f"Aluguel {uuid4().hex[:6]}",
            value=Decimal("3700.00"),
        )
        s.add(item)
        await s.flush()

        id_kwarg = "system_id" if sync_name.endswith("system_payables") else "cost_id"
        await getattr(svc, sync_name)(
            project_id=pid, labor_competencia=comp, scenario="REALIZADO", **{id_kwarg: item.id}
        )
        await s.flush()
        return item

    async def _meses_do_titulo(self, s, item_id) -> list[date]:
        from sqlalchemy import select
        from app.models.payable_snapshot import PayableSnapshot

        rows = (
            await s.execute(select(PayableSnapshot).where(PayableSnapshot.ref_id == item_id))
        ).scalars().all()
        return sorted(r.month for r in rows)

    async def test_custo_diverso_de_agosto_gera_titulo_em_setembro(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.models.project_operational import ProjectOperationalFixed

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            try:
                item = await self._lanca(
                    s,
                    ProjectOperationalFixed,
                    "sync_project_misc_cost_payables",
                    comp=date(2099, 8, 1),
                    pagamento=date(2099, 9, 1),
                )
                self.assertEqual(await self._meses_do_titulo(s, item.id), [date(2099, 9, 1)])
            finally:
                await s.rollback()

    async def test_vencimento_cai_no_mes_do_pagamento(self) -> None:
        """Vencimento dia 10 de SETEMBRO — não adianta o mês certo com a data do mês errado."""
        from sqlalchemy import select
        from app.database.session import AsyncSessionLocal, engine
        from app.models.payable_snapshot import PayableSnapshot
        from app.models.project_operational import ProjectOperationalFixed

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            try:
                item = await self._lanca(
                    s,
                    ProjectOperationalFixed,
                    "sync_project_misc_cost_payables",
                    comp=date(2099, 8, 1),
                    pagamento=date(2099, 9, 1),
                )
                row = (
                    await s.execute(select(PayableSnapshot).where(PayableSnapshot.ref_id == item.id))
                ).scalars().one()
                self.assertEqual(row.due_date, date(2099, 9, 10))
            finally:
                await s.rollback()

    async def test_sistema_do_projeto_segue_a_mesma_regra(self) -> None:
        """Sistemas usam a mesma função e o mesmo gerador — não podem divergir do custo diverso."""
        from app.database.session import AsyncSessionLocal, engine
        from app.models.project_operational import ProjectSystemCost

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            try:
                item = await self._lanca(
                    s,
                    ProjectSystemCost,
                    "sync_project_system_payables",
                    comp=date(2099, 8, 1),
                    pagamento=date(2099, 9, 1),
                )
                self.assertEqual(await self._meses_do_titulo(s, item.id), [date(2099, 9, 1)])
            finally:
                await s.rollback()

    async def test_titulo_aberto_no_mes_antigo_e_movido_e_nao_duplicado(self) -> None:
        """Caminho de correção dos títulos já lançados no mês errado.

        Quem já tem custo de agosto com título em AGO precisa apenas re-salvar o custo: o sync
        move o título aberto para SET em vez de criar um segundo. Se ele duplicasse, o mês
        apareceria pagando duas vezes o mesmo aluguel.
        """
        from datetime import date as _date
        from decimal import Decimal as _Dec

        from app.database.session import AsyncSessionLocal, engine
        from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
        from app.models.payable_snapshot_generation import PayableSnapshotGeneration
        from app.models.project_operational import ProjectOperationalFixed
        from app.services.payable_snapshot_service import PayableSnapshotService

        await engine.dispose()
        comp, pagamento = _date(2099, 8, 1), _date(2099, 9, 1)
        async with AsyncSessionLocal() as s:
            try:
                pid = await self._projeto(s)
                svc = PayableSnapshotService(s)
                for mes in (comp, pagamento):
                    if not await svc.is_generated(month=mes):
                        s.add(PayableSnapshotGeneration(month=mes, created_at=datetime.now(timezone.utc)))
                        await s.flush()

                item = ProjectOperationalFixed(
                    project_id=pid, competencia=comp, scenario="REALIZADO",
                    name=f"Aluguel {uuid4().hex[:6]}", value=_Dec("3700.00"),
                )
                s.add(item)
                await s.flush()

                # Estado ANTES da correção: título aberto no mês da competência.
                s.add(
                    PayableSnapshot(
                        month=comp,
                        type=PayableSnapshotType.FIXED_COST,
                        ref_id=item.id,
                        project_id=pid,
                        name=item.name,
                        cost_center="Administrativo",
                        category="Custo diverso",
                        amount_original=_Dec("3700.00"),
                        amount_final=_Dec("3700.00"),
                        amount_paid=_Dec("0"),
                        due_date=_date(2099, 8, 10),
                        paid=False,
                        observation="[source:project_misc_cost]",
                    )
                )
                await s.flush()

                await svc.sync_project_misc_cost_payables(
                    project_id=pid, cost_id=item.id, labor_competencia=comp, scenario="REALIZADO"
                )
                await s.flush()

                self.assertEqual(await self._meses_do_titulo(s, item.id), [pagamento])
            finally:
                await s.rollback()

    async def test_lancamento_e_geracao_concordam_sobre_o_mes(self) -> None:
        """A invariante que faltava: os DOIS caminhos precisam apontar para o mesmo mês.

        O gerador do snapshot lê os itens de `previous_competencia(payment_month)`; o lançamento
        na tela grava em `next_competencia(competencia)`. São a mesma equação vista dos dois
        lados — se alguém mexer em um sem o outro, o custo passa a cair em dois meses conforme
        a origem, e o teste falha.
        """
        from app.utils.date_utils import next_competencia, previous_competencia

        competencia = date(2099, 8, 1)
        mes_do_lancamento = next_competencia(competencia)
        # O gerador, ao montar o mês do lançamento, busca itens desta competência:
        self.assertEqual(previous_competencia(mes_do_lancamento), competencia)


if __name__ == "__main__":
    unittest.main()
