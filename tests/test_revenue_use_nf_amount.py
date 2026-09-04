"""Faturamento: `use_nf_amount` troca a fonte do valor por LANÇAMENTO.

Marcado, o lançamento passa a valer a soma do BRUTO das NFs FATURADAS da mesma competência do
projeto — pré-faturada (`is_official = false`) e cancelada ficam de fora, e a competência vem de
`competence_month`, nunca do mês da emissão (a NF é emitida ~1 mês depois do serviço).

A retenção acompanha a MESMA base: em modo NF os 10% incidem sobre a soma faturada, senão
receita e retenção viriam de origens diferentes no mesmo mês.

O valor manual (`amount`) nunca é sobrescrito — desmarcar devolve o número original.

Teste de banco: NÃO commita (rollback ao final).
"""

from __future__ import annotations

import unittest
from datetime import date


class RevenueUseNfAmountTests(unittest.IsolatedAsyncioTestCase):
    async def _fixture(self, s):
        """Um projeto com faturamento manual e NFs de várias naturezas na mesma competência."""
        from sqlalchemy import select
        from app.models.financial import Revenue
        from app.models.project import Project
        from app.models.receivable import ReceivableInvoice

        proj = (await s.execute(select(Project).limit(1))).scalars().first()
        if proj is None:
            self.skipTest("banco sem projeto")
        comp = date(2099, 3, 1)  # competência fora do histórico real

        rev = Revenue(
            project_id=proj.id,
            competencia=comp,
            scenario="REALIZADO",
            amount=100_000.00,
            description="teste use_nf_amount",
            status="recebido",
            has_retention=True,
        )
        s.add(rev)

        def nf(number: str, gross: float, *, official: bool, status: str, competence: date | None):
            return ReceivableInvoice(
                project_id=proj.id,
                nf_number=number,
                issue_date=date(2099, 4, 10),  # emitida no mês SEGUINTE, como na vida real
                due_date=date(2099, 7, 10),
                due_days=90,
                competence_month=competence,
                gross_amount=gross,
                net_amount=round(gross * 0.9385, 2),
                is_official=official,
                invoice_status=status,
            )

        s.add_all(
            [
                nf("T-9001", 60_000.00, official=True, status="EMITIDA", competence=comp),
                nf("T-9002", 20_000.00, official=True, status="ANTECIPADA", competence=comp),
                # Ruído que NÃO pode entrar na soma:
                nf("T-9003", 500_000.00, official=False, status="EMITIDA", competence=comp),  # pré-faturada
                nf("T-9004", 700_000.00, official=True, status="CANCELADA", competence=comp),  # cancelada
                nf("T-9005", 900_000.00, official=True, status="EMITIDA", competence=None),  # sem competência
                nf("T-9006", 800_000.00, official=True, status="EMITIDA", competence=date(2099, 4, 1)),  # outro mês
            ]
        )
        await s.flush()
        return proj, comp, rev

    async def _run(self, body) -> None:
        from app.database.session import AsyncSessionLocal, engine

        # Cada teste roda em um event loop próprio (IsolatedAsyncioTestCase) e o pool do engine
        # fica preso ao loop anterior — descartar antes de abrir a sessão é a convenção usada
        # nos demais testes de banco do projeto.
        await engine.dispose()
        async with AsyncSessionLocal() as s:
            try:
                await body(s)
            finally:
                await s.rollback()

    async def test_desmarcado_usa_o_valor_manual(self) -> None:
        async def body(s):
            from app.services.financial_service import FinancialService

            proj, comp, _rev = await self._fixture(s)
            svc = FinancialService(s)
            receita = await svc.calcular_receita_total(
                project_id=proj.id, competencia=comp, scenario="REALIZADO"
            )
            retencao = await svc.calcular_total_retencao(
                project_id=proj.id, competencia=comp, scenario="REALIZADO"
            )
            self.assertAlmostEqual(receita, 100_000.00, places=2)
            self.assertAlmostEqual(retencao, 10_000.00, places=2)

        await self._run(body)

    async def test_marcado_usa_a_soma_das_nfs_faturadas(self) -> None:
        async def body(s):
            from app.services.financial_service import FinancialService

            proj, comp, rev = await self._fixture(s)
            rev.use_nf_amount = True
            await s.flush()

            svc = FinancialService(s)
            receita = await svc.calcular_receita_total(
                project_id=proj.id, competencia=comp, scenario="REALIZADO"
            )
            retencao = await svc.calcular_total_retencao(
                project_id=proj.id, competencia=comp, scenario="REALIZADO"
            )
            # 60.000 (EMITIDA) + 20.000 (ANTECIPADA). Ficam de fora: pré-faturada, cancelada,
            # sem competência e a de outro mês — se qualquer uma entrar, o número estoura.
            self.assertAlmostEqual(receita, 80_000.00, places=2)
            self.assertAlmostEqual(retencao, 8_000.00, places=2)

        await self._run(body)

    async def test_manual_permanece_intacto_ao_marcar(self) -> None:
        async def body(s):
            proj, comp, rev = await self._fixture(s)
            rev.use_nf_amount = True
            await s.flush()
            await s.refresh(rev)
            self.assertAlmostEqual(float(rev.amount), 100_000.00, places=2)

        await self._run(body)

    async def test_marcado_sem_nf_no_mes_da_zero(self) -> None:
        """Marcar é escolher "usar o que foi faturado"; sem nota, é zero — não o manual.

        Cair de volta no valor manual esconderia do gestor que não há NF nenhuma no mês, que é
        justamente o que a conciliação existe para mostrar.
        """

        async def body(s):
            from sqlalchemy import select
            from app.models.financial import Revenue
            from app.models.project import Project
            from app.services.financial_service import FinancialService

            proj = (await s.execute(select(Project).limit(1))).scalars().first()
            if proj is None:
                self.skipTest("banco sem projeto")
            comp = date(2099, 11, 1)
            s.add(
                Revenue(
                    project_id=proj.id,
                    competencia=comp,
                    scenario="REALIZADO",
                    amount=50_000.00,
                    description="teste sem NF",
                    status="recebido",
                    has_retention=True,
                    use_nf_amount=True,
                )
            )
            await s.flush()

            svc = FinancialService(s)
            receita = await svc.calcular_receita_total(
                project_id=proj.id, competencia=comp, scenario="REALIZADO"
            )
            retencao = await svc.calcular_total_retencao(
                project_id=proj.id, competencia=comp, scenario="REALIZADO"
            )
            self.assertAlmostEqual(receita, 0.0, places=2)
            self.assertAlmostEqual(retencao, 0.0, places=2)

        await self._run(body)


if __name__ == "__main__":
    unittest.main()
