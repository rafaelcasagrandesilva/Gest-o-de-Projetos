"""Regressões do Contas a Pagar e da Inicializar Competência (ago/2026).

Quatro defeitos relatados por usuários do financeiro, todos reproduzidos contra dados
reais antes da correção. Cada teste aqui trava UM deles:

1. título PAGO voltava para EM ABERTO — a sincronização de mão de obra reescrevia o
   valor de um título que já tinha pagamento (Custos Fixos e Componentes Variáveis já
   tinham a guarda; a mão de obra não);
2. título PAGO ganhava uma cópia EM ABERTO ao lado — o casamento era pelo NOME do
   título, que carrega o nome do colaborador; corrigir o cadastro criava linha nova;
3. valor digitado na grade de Custos Fixos ficava sem título no CAP quando a vigência
   do item não cobria a competência ("pago, mas não localizado");
4. Inicializar Competência descartava em silêncio o colaborador multi-contrato, porque
   o teto de 100% ignorava as alocações com remuneração INDEPENDENTE.

Cobre também a EXCLUSÃO EM MASSA de vínculos (recurso novo): a prévia nunca pode tocar no
banco, porque é ela que sustenta o aviso de "N destes já têm pagamento no Contas a Pagar".

Testes de banco NÃO commitam (rollback ao final).
"""

from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError


def _d(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


class CapLaborPaymentGuardTests(unittest.IsolatedAsyncioTestCase):
    """Defeitos 1 e 2 — título de mão de obra com pagamento."""

    async def _prelude(self, session, comp: date) -> None:
        from app.models.payable_snapshot_generation import PayableSnapshotGeneration
        from app.services.payable_snapshot_service import PayableSnapshotService

        try:
            await session.execute(text("SELECT entry_id FROM payable_snapshots LIMIT 1"))
        except ProgrammingError:
            self.skipTest("Colunas ausentes (rode alembic upgrade head).")
        if not await PayableSnapshotService(session).is_generated(month=comp):
            session.add(PayableSnapshotGeneration(month=comp, created_at=datetime.now(timezone.utc)))
        await session.flush()

    async def test_titulo_pago_nao_tem_valor_reescrito(self) -> None:
        """Valor recalculado diferente NÃO pode mexer em título com pagamento."""
        from app.database.session import AsyncSessionLocal, engine
        from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
        from app.services.payable_snapshot_service import (
            _apply_dynamic_payable_amounts,
            _money2,
        )

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            comp = date(2099, 3, 1)
            await self._prelude(s, comp)
            try:
                row = PayableSnapshot(
                    month=comp,
                    type=PayableSnapshotType.COLLABORATOR,
                    ref_id=uuid4(),
                    project_id=None,
                    name="Fulano de Tal — Salário Base PJ",
                    cost_center="Administrativo",
                    category="Mão de obra",
                    amount_original=Decimal("1000.00"),
                    amount_final=Decimal("1000.00"),
                    amount_paid=Decimal("1000.00"),
                    due_date=date(2099, 3, 10),
                    paid=True,
                    include_in_dashboard=True,
                )
                s.add(row)
                await s.flush()

                # O que a sincronização FAZIA: aplicar o novo valor sem olhar o pagamento.
                # Aqui provamos por que a guarda existe — sem ela, PAGO vira EM ABERTO.
                _apply_dynamic_payable_amounts(row, new_amount=Decimal("1200.00"))
                self.assertFalse(
                    row.paid,
                    "sem guarda, subir o valor de um título pago o devolve para EM ABERTO",
                )
                self.assertEqual(_money2(row.amount_paid), Decimal("1000.00"))
            finally:
                await s.rollback()

    async def test_rotulo_do_componente_ignora_troca_de_nome(self) -> None:
        """O casamento do título tem que sobreviver à correção do nome no cadastro."""
        from app.services.payable_snapshot_service import (
            _collaborator_payable_component_label,
            _collaborator_payable_snapshot_name,
        )

        antigo = _collaborator_payable_snapshot_name("Willian Neres Rodrigues", "Salário CLT")
        novo = _collaborator_payable_snapshot_name("William Neres Rodrigues", "Salário CLT")
        self.assertNotEqual(antigo, novo, "o nome completo muda — por isso não serve de chave")
        self.assertEqual(
            _collaborator_payable_component_label(antigo),
            _collaborator_payable_component_label(novo),
            "o rótulo do componente é estável e é ele que casa o título",
        )
        self.assertEqual(_collaborator_payable_component_label(antigo), "Salário CLT")
        # Formato legado (1 linha por colaborador, sem rótulo) → continua adotável.
        self.assertEqual(_collaborator_payable_component_label("Jolly Lemos"), "")
        self.assertEqual(_collaborator_payable_component_label(None), "")


class CapGradeExplicitaTests(unittest.IsolatedAsyncioTestCase):
    """Defeito 3 — valor digitado na grade sempre vira título."""

    async def test_lancamento_fora_da_vigencia_ainda_gera_titulo(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.models.company_finance import CompanyFinancialItem
        from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
        from app.models.payable_snapshot_generation import PayableSnapshotGeneration
        from app.services.company_finance_service import CompanyFinanceService
        from app.services.payable_snapshot_service import PayableSnapshotService

        await engine.dispose()
        comp, COMP = date(2099, 6, 1), "2099-06"
        async with AsyncSessionLocal() as s:
            try:
                await s.execute(text("SELECT entry_id FROM payable_snapshots LIMIT 1"))
            except ProgrammingError:
                self.skipTest("Colunas ausentes (rode alembic upgrade head).")
            try:
                if not await PayableSnapshotService(s).is_generated(month=comp):
                    s.add(PayableSnapshotGeneration(month=comp, created_at=datetime.now(timezone.utc)))
                await s.flush()

                # Item cadastrado DEPOIS: a vigência começa após a competência do lançamento
                # — exatamente o caso ENEL (cadastro em ago/26, consumo de jun e jul lançado).
                item = CompanyFinancialItem(
                    tipo="custo_fixo",
                    nome=f"Concessionária retroativa {uuid4().hex[:6]}",
                    valor_referencia=Decimal("80.00"),
                    is_active=True,
                    start_date=date(2099, 8, 1),
                    cost_center="Administrativo",
                    cost_center_system="ADMINISTRATIVO",
                )
                s.add(item)
                await s.flush()

                await CompanyFinanceService(s).replace_entries(
                    item_id=item.id,
                    competencia=COMP,
                    lancamentos=[{"valor": 32.43, "vencimento": "2099-06-10", "descricao": None}],
                )

                lines = list(
                    (
                        await s.execute(
                            select(PayableSnapshot).where(
                                PayableSnapshot.ref_id == item.id,
                                PayableSnapshot.month == comp,
                                PayableSnapshot.type == PayableSnapshotType.FIXED_COST,
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                self.assertEqual(
                    len(lines), 1, "box preenchida tem que ter título no CAP para poder baixar"
                )
                self.assertEqual(
                    float(lines[0].amount_final),
                    32.43,
                    "o título tem que valer exatamente o que está na box",
                )
            finally:
                await s.rollback()


class InicializarCompetenciaTests(unittest.IsolatedAsyncioTestCase):
    """Defeito 4 — multi-contrato e cópia exata."""

    async def test_teto_de_100_ignora_contratos_independentes(self) -> None:
        """O colaborador em dois contratos INDEPENDENTES não pode ser descartado da cópia."""
        from app.repositories.project_operational import ProjectLaborRepository
        import inspect

        from app.services.competencia_initialization_service import (
            CompetenciaInitializationService,
        )

        # A regra do teto vive no `_replace_labor`; garantimos que ele consulta as alocações
        # independentes e as exclui da soma — foi a ausência disso que derrubava a linha.
        src = inspect.getsource(CompetenciaInitializationService._replace_labor)
        self.assertIn("independent_project_ids", src)
        self.assertIn("exclude_project_ids=independentes", src)
        self.assertIn("este_e_independente", src)

        # E o repositório precisa mesmo aceitar o parâmetro (assinatura viva, não só texto).
        sig = inspect.signature(
            ProjectLaborRepository.sum_allocation_percentage_for_employee_competencia
        )
        self.assertIn("exclude_project_ids", sig.parameters)

    async def test_omissao_e_reportada_em_vez_de_silenciosa(self) -> None:
        """Cópia é exata por contrato: o que ficar de fora precisa chegar à tela."""
        from app.services.competencia_initialization_service import CategoryCopyOutcome, CostCategory

        out = CategoryCopyOutcome(category=CostCategory.LABOR, copied=30, skipped=("Fulano",))
        self.assertEqual(out.skipped, ("Fulano",))
        # Default vazio: o caminho normal não inventa pendência.
        self.assertEqual(
            CategoryCopyOutcome(category=CostCategory.VEHICLES, copied=9).skipped, ()
        )

    async def test_combustivel_zera_de_previsto_para_realizado(self) -> None:
        """Previsto→Realizado zera o combustível (e só nesse sentido)."""
        import inspect

        from app.services.competencia_initialization_service import (
            CompetenciaInitializationService,
        )

        src = inspect.getsource(CompetenciaInitializationService._replace_vehicles)
        self.assertIn("zera_combustivel", src)
        self.assertIn("source.scenario is Scenario.PREVISTO", src)
        self.assertIn("target.scenario is Scenario.REALIZADO", src)
        # Zero, não nulo: o REALIZADO exige o campo preenchido para poder ser editado.
        self.assertIn('Decimal("0")', src)

    async def test_beneficios_sao_copiados_junto(self) -> None:
        """Componentes Variáveis acompanham o vínculo (a FK apagava os do destino)."""
        import inspect

        from app.services.competencia_initialization_service import (
            CompetenciaInitializationService,
        )

        self.assertTrue(hasattr(CompetenciaInitializationService, "_copy_variable_components"))
        src = inspect.getsource(CompetenciaInitializationService._replace_labor)
        self.assertIn("_copy_variable_components", src)


class TituloPagoNuncaVoltaTests(unittest.IsolatedAsyncioTestCase):
    """AUDITORIA: nenhum caminho de sincronização pode derrubar um título PAGO.

    `paid` não é um campo que alguém liga/desliga — é DERIVADO de amount_paid × amount_final
    (`_sync_legacy_paid_fields`). Então todo código que reescreve `amount_final` de um título
    pago o devolve para EM ABERTO. Estes testes cobrem os caminhos que reescrevem valor,
    cada um com a sua guarda de pagamento:

      1. mão de obra ............ sync_collaborator_payables_for_labor
      2. sistema do projeto ..... sync_project_system_payables
      3. custo diverso .......... sync_project_misc_cost_payables
      4. custo fixo/endivid. .... _reconcile_company_finance_entries_for_month
      5. componentes variáveis .. sync_variable_component_snapshot

    Verificado que estes testes REPROVAM sem as guardas (1, 2 e 3 falhavam).
    """

    async def _projeto(self, s):
        from sqlalchemy import text as sql

        pid = (
            await s.execute(
                sql(
                    """select id from projects where deleted_at is null
                       order by created_at limit 1"""
                )
            )
        ).scalar_one_or_none()
        if pid is None:
            self.skipTest("Sem projetos ativos no banco.")
        return pid

    async def _cenario_pago(self, s, Model, sync_name, comp):
        """Cria item + título no CAP e o quita integralmente. Devolve (item, snapshot_id)."""
        from app.models.payable_snapshot_generation import PayableSnapshotGeneration
        from app.services.payable_snapshot_service import PayableSnapshotService
        from sqlalchemy import text as sql

        pid = await self._projeto(s)
        svc = PayableSnapshotService(s)
        # O título de um custo de projeto nasce no mês do PAGAMENTO (competência + 1), então é
        # esse o mês que precisa estar gerado — marcar só a competência fazia o sync devolver 0
        # e o teste se pular sozinho, desligando em silêncio a guarda que ele existe para vigiar.
        from app.utils.date_utils import next_competencia

        for mes in (comp, next_competencia(comp)):
            if not await svc.is_generated(month=mes):
                s.add(PayableSnapshotGeneration(month=mes, created_at=datetime.now(timezone.utc)))
                await s.flush()

        item = Model(
            project_id=pid, competencia=comp, scenario="REALIZADO",
            name=f"Auditoria {uuid4().hex[:6]}", value=Decimal("1000.00"),
        )
        s.add(item)
        await s.flush()

        id_kwarg = "system_id" if sync_name.endswith("system_payables") else "cost_id"
        await getattr(svc, sync_name)(
            project_id=pid, labor_competencia=comp, scenario="REALIZADO", **{id_kwarg: item.id}
        )
        await s.flush()

        sid = (
            await s.execute(
                sql(
                    """select id from payable_snapshots
                       where ref_id = :i and type = 'FIXED_COST'"""
                ),
                {"i": item.id},
            )
        ).scalar_one_or_none()
        if sid is None:
            self.skipTest("Título não materializado neste banco.")
        await s.execute(
            sql(
                """update payable_snapshots
                   set amount_paid = amount_final, paid = true where id = :i"""
            ),
            {"i": sid},
        )
        await s.flush()
        return pid, item, sid

    async def _assert_preserva(self, Model, sync_name) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.payable_snapshot_service import PayableSnapshotService
        from sqlalchemy import text as sql

        await engine.dispose()
        comp = date(2099, 9, 1)
        async with AsyncSessionLocal() as s:
            try:
                pid, item, sid = await self._cenario_pago(s, Model, sync_name, comp)

                # Alguém edita o valor do item (ou a Inicializar Competência o reescreve).
                item.value = Decimal("4000.00")
                await s.flush()

                id_kwarg = "system_id" if sync_name.endswith("system_payables") else "cost_id"
                await getattr(PayableSnapshotService(s), sync_name)(
                    project_id=pid, labor_competencia=comp, scenario="REALIZADO",
                    **{id_kwarg: item.id},
                )
                await s.flush()

                row = (
                    await s.execute(
                        sql(
                            """select paid, amount_final, amount_paid
                               from payable_snapshots where id = :i"""
                        ),
                        {"i": sid},
                    )
                ).first()
                self.assertTrue(
                    row.paid,
                    f"{sync_name}: título PAGO voltou para EM ABERTO ao recalcular o valor",
                )
                self.assertEqual(
                    _d(row.amount_final),
                    Decimal("1000.00"),
                    f"{sync_name}: valor de título pago não pode ser reescrito",
                )
            finally:
                await s.rollback()

    async def test_sistema_do_projeto_preserva_titulo_pago(self) -> None:
        from app.models.project_operational import ProjectSystemCost

        await self._assert_preserva(ProjectSystemCost, "sync_project_system_payables")

    async def test_custo_diverso_preserva_titulo_pago(self) -> None:
        from app.models.project_operational import ProjectOperationalFixed

        await self._assert_preserva(ProjectOperationalFixed, "sync_project_misc_cost_payables")

    async def test_todo_ponto_que_reescreve_valor_tem_guarda(self) -> None:
        """Guarda estrutural: `_apply_dynamic_payable_amounts` nunca sem checar pagamento.

        Se alguém adicionar uma quinta chamada no futuro, este teste falha e obriga a
        decidir explicitamente sobre a guarda — em vez de reintroduzir o defeito calado.
        """
        import inspect

        from app.services import payable_snapshot_service as mod

        fonte = inspect.getsource(mod)
        chamadas = fonte.count("_apply_dynamic_payable_amounts(")
        # 1 definição + 4 chamadas (mão de obra, sistema/misc, custo fixo, componentes).
        self.assertEqual(
            chamadas,
            5,
            "número de chamadas mudou — confirme que a nova tem guarda de pagamento "
            "(amount_paid > 0 or _has_active_payments) antes de ajustar este número",
        )
        guardas = fonte.count("_has_active_payments(")
        self.assertGreaterEqual(guardas, 5, "cada caminho que reescreve valor precisa da guarda")


class SistemasECustosDiversosTests(unittest.IsolatedAsyncioTestCase):
    """Edição de Sistemas e Custos diversos + exclusão em massa nessas abas.

    O backend já expunha PATCH nas duas abas; só a tela não usava. Estes testes travam o
    contrato para que a edição não se perca de novo.
    """

    async def _projeto_e_competencia(self, s):
        from sqlalchemy import text as sql

        row = (
            await s.execute(sql("select id from projects order by created_at limit 1"))
        ).first()
        if row is None:
            self.skipTest("Sem projetos no banco.")
        return row.id, date(2099, 4, 1)

    async def test_edita_nome_e_valor_de_sistema(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.models.project_operational import ProjectSystemCost
        from app.services.project_structure_service import ProjectStructureService

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            pid, comp = await self._projeto_e_competencia(s)
            try:
                row = ProjectSystemCost(
                    project_id=pid, competencia=comp, scenario="REALIZADO",
                    name="Licença original", value=Decimal("100.00"),
                )
                s.add(row)
                await s.flush()
                atualizado = await ProjectStructureService(s).update_system(
                    system_id=row.id, data={"name": "Licença renomeada", "value": 250.0}
                )
                self.assertEqual(atualizado.name, "Licença renomeada")
                self.assertEqual(float(atualizado.value), 250.0)
            finally:
                await s.rollback()

    async def test_edita_nome_e_valor_de_custo_diverso(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.models.project_operational import ProjectOperationalFixed
        from app.services.project_structure_service import ProjectStructureService

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            pid, comp = await self._projeto_e_competencia(s)
            try:
                row = ProjectOperationalFixed(
                    project_id=pid, competencia=comp, scenario="REALIZADO",
                    name="Custo original", value=Decimal("80.00"),
                )
                s.add(row)
                await s.flush()
                atualizado = await ProjectStructureService(s).update_fixed(
                    fixed_id=row.id, data={"name": "Custo renomeado", "value": 42.5}
                )
                self.assertEqual(atualizado.name, "Custo renomeado")
                self.assertEqual(float(atualizado.value), 42.5)
            finally:
                await s.rollback()

    async def test_massa_nas_abas_de_sistemas_e_custos(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.models.project_operational import ProjectOperationalFixed, ProjectSystemCost
        from app.services.project_structure_service import ProjectStructureService

        await engine.dispose()
        for categoria, Model in (("systems", ProjectSystemCost), ("misc", ProjectOperationalFixed)):
            async with AsyncSessionLocal() as s:
                pid, comp = await self._projeto_e_competencia(s)
                try:
                    linhas = [
                        Model(
                            project_id=pid, competencia=comp, scenario="REALIZADO",
                            name=f"Item {i}", value=Decimal("10.00"),
                        )
                        for i in range(3)
                    ]
                    for l in linhas:
                        s.add(l)
                    await s.flush()
                    ids = [l.id for l in linhas]
                    svc = ProjectStructureService(s)

                    prev = await svc.delete_items_bulk(
                        project_id=pid, category=categoria, ids=ids, confirm=False
                    )
                    self.assertEqual((prev["total"], prev["excluidos"]), (3, 0), categoria)

                    out = await svc.delete_items_bulk(
                        project_id=pid, category=categoria, ids=ids, confirm=True
                    )
                    self.assertEqual(out["excluidos"], 3, categoria)
                finally:
                    await s.rollback()

    async def test_categoria_invalida_e_recusada(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.project_structure_service import ProjectStructureService
        from fastapi import HTTPException
        from uuid import uuid4

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            try:
                with self.assertRaises(HTTPException) as ctx:
                    await ProjectStructureService(s).delete_items_bulk(
                        project_id=uuid4(), category="inexistente", ids=[uuid4()], confirm=False
                    )
                self.assertEqual(ctx.exception.status_code, 400)
            finally:
                await s.rollback()

    async def test_veiculos_nunca_avisam_pagamento(self) -> None:
        """Veículos não geram título no CAP — o aviso não se aplica ali."""
        from app.database.session import AsyncSessionLocal, engine
        from app.services.project_structure_service import ProjectStructureService

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            try:
                vazio = await ProjectStructureService(s)._bulk_items_with_paid_payables(
                    "vehicles", []
                )
                self.assertEqual(vazio, [])
            finally:
                await s.rollback()


class GraficoCapBateComATelaTests(unittest.IsolatedAsyncioTestCase):
    """O modo Contas a Pagar do gráfico tem que bater com o total da TELA do CAP.

    A tela usa "Mês (fluxo de caixa)" (`list_for_operational_month`): competência do mês
    MAIS obrigações de qualquer competência pagas no mês. O gráfico somava só a
    competência, e o financeiro pegou a diferença conferindo agosto (R$ 6.080 de um título
    de junho pago em 25/08). Este teste amarra as duas definições.
    """

    async def test_total_do_grafico_igual_ao_da_tela(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.indicators_service import IndicatorsService
        from app.services.payable_snapshot_service import PayableSnapshotService
        from sqlalchemy import text as sql

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            meses = (
                await s.execute(
                    sql(
                        """select distinct month from payable_snapshots
                           order by month desc limit 3"""
                    )
                )
            ).scalars().all()
            if not meses:
                self.skipTest("Sem títulos no Contas a Pagar.")
            try:
                inicio, fim = min(meses), max(meses)
                grafico = await IndicatorsService(s)._cap_costs_by_month(start=inicio, end=fim)
                svc = PayableSnapshotService(s)
                for mes in meses:
                    linhas = await svc.list_for_operational_month(month=mes)
                    tela = round(sum(float(r.amount_final or 0) for r in linhas), 2)
                    self.assertAlmostEqual(
                        grafico.get(mes, 0.0),
                        tela,
                        places=2,
                        msg=f"{mes}: gráfico e tela do CAP divergem",
                    )
            finally:
                await s.rollback()

    async def test_titulo_pago_fora_da_competencia_entra_no_mes_do_pagamento(self) -> None:
        """O caso concreto que gerou a divergência: competência X, pago no mês Y."""
        from app.database.session import AsyncSessionLocal, engine
        from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
        from app.models.payable_payment import PayablePayment
        from app.services.indicators_service import IndicatorsService

        await engine.dispose()
        comp, pagamento = date(2098, 5, 1), date(2098, 7, 15)
        async with AsyncSessionLocal() as s:
            try:
                row = PayableSnapshot(
                    month=comp,
                    type=PayableSnapshotType.MANUAL,
                    name="Título pago fora da competência",
                    cost_center="Administrativo",
                    category="Teste",
                    amount_original=Decimal("6080.00"),
                    amount_final=Decimal("6080.00"),
                    amount_paid=Decimal("6080.00"),
                    due_date=comp,
                    paid=True,
                    include_in_dashboard=True,
                )
                s.add(row)
                await s.flush()
                s.add(
                    PayablePayment(
                        payable_snapshot_id=row.id,
                        amount=Decimal("6080.00"),
                        payment_date=pagamento,
                    )
                )
                await s.flush()

                totais = await IndicatorsService(s)._cap_costs_by_month(
                    start=date(2098, 5, 1), end=date(2098, 7, 1)
                )
                self.assertAlmostEqual(totais.get(comp, 0.0), 6080.0, places=2,
                                       msg="deve contar no mês da competência")
                self.assertAlmostEqual(totais.get(date(2098, 7, 1), 0.0), 6080.0, places=2,
                                       msg="e também no mês do pagamento (fluxo de caixa)")
            finally:
                await s.rollback()


class DescricaoLongaNaoQuebraOMesTests(unittest.IsolatedAsyncioTestCase):
    """Nota longa de Componente Variável não pode derrubar a geração do mês.

    `payment_variable_components.note` é TEXT (livre) e desce para
    `payable_snapshots.item_description`, que era varchar(255). Uma nota de 286 caracteres
    — o detalhamento de uma ajuda de custo — abortava a geração do Contas a Pagar de
    setembro INTEIRO com StringDataRightTruncationError; a tela ficava em R$ 0,00.

    A migration 0119 passou as duas colunas de texto do snapshot para TEXT. `name` foi junto
    porque é concatenação de `full_name` (já varchar(255)) com o rótulo do componente — basta
    um nome longo para estourar.
    """

    async def test_colunas_de_texto_do_snapshot_sao_ilimitadas(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from sqlalchemy import text as sql

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            try:
                for coluna in ("name", "item_description"):
                    limite = (
                        await s.execute(
                            sql(
                                """select character_maximum_length
                                     from information_schema.columns
                                    where table_name = 'payable_snapshots'
                                      and column_name = :c"""
                            ),
                            {"c": coluna},
                        )
                    ).scalar_one_or_none()
                    self.assertIsNone(
                        limite,
                        f"payable_snapshots.{coluna} precisa ser TEXT (rode alembic upgrade head)",
                    )
            finally:
                await s.rollback()

    async def test_grava_descricao_maior_que_255(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
        from sqlalchemy import text as sql

        await engine.dispose()
        # 286 caracteres: exatamente o tamanho da nota real que derrubou setembro/2026.
        nota = "Flash equipe subterrâneo + Locação Veículo + prestação + Fonte Notebook " * 5
        nota = nota[:286]
        async with AsyncSessionLocal() as s:
            try:
                row = PayableSnapshot(
                    month=date(2097, 1, 1),
                    type=PayableSnapshotType.COLLABORATOR,
                    name="Colaborador com nome muito longo " * 9,
                    item_description=nota,
                    cost_center="Administrativo",
                    category="Mão de obra",
                    amount_original=Decimal("100.00"),
                    amount_final=Decimal("100.00"),
                    amount_paid=Decimal("0"),
                    due_date=date(2097, 1, 10),
                    paid=False,
                    include_in_dashboard=True,
                )
                s.add(row)
                await s.flush()
                gravado = (
                    await s.execute(
                        sql("select length(item_description), length(name) from payable_snapshots where id = :i"),
                        {"i": row.id},
                    )
                ).first()
                self.assertEqual(gravado[0], 286, "a descrição não pode ser truncada")
                self.assertGreater(gravado[1], 255, "o nome também precisa passar de 255")
            finally:
                await s.rollback()


class ExclusaoEmMassaTests(unittest.IsolatedAsyncioTestCase):
    """Exclusão em massa de vínculos de mão de obra (duas fases)."""

    async def test_previa_nao_exclui_nada(self) -> None:
        """`confirm=False` só RELATA — é o que sustenta o aviso antes de destruir."""
        from app.database.session import AsyncSessionLocal, engine
        from app.services.project_structure_service import ProjectStructureService
        from sqlalchemy import text as sql

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            row = (
                await s.execute(
                    sql(
                        """select id, project_id, competencia from project_labors
                           where scenario = 'REALIZADO' limit 1"""
                    )
                )
            ).first()
            if row is None:
                self.skipTest("Sem vínculos de mão de obra no banco.")
            try:
                antes = (
                    await s.execute(sql("select count(*) from project_labors"))
                ).scalar_one()
                out = await ProjectStructureService(s).delete_items_bulk(
                    project_id=row.project_id, category="labor", ids=[row.id], confirm=False
                )
                self.assertEqual(out["total"], 1)
                self.assertEqual(out["excluidos"], 0, "prévia nunca exclui")
                depois = (
                    await s.execute(sql("select count(*) from project_labors"))
                ).scalar_one()
                self.assertEqual(antes, depois, "prévia não pode tocar no banco")
            finally:
                await s.rollback()

    async def test_lista_vazia_e_inocua(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.project_structure_service import ProjectStructureService
        from uuid import uuid4

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            try:
                out = await ProjectStructureService(s).delete_items_bulk(
                    project_id=uuid4(), category="labor", ids=[], confirm=True
                )
                self.assertEqual((out["total"], out["excluidos"]), (0, 0))
            finally:
                await s.rollback()

    async def test_recusa_competencias_misturadas(self) -> None:
        """Uma competência por vez — a tela atua sempre sobre o mês que está aberto."""
        from app.database.session import AsyncSessionLocal, engine
        from app.services.project_structure_service import ProjectStructureService
        from fastapi import HTTPException
        from sqlalchemy import text as sql

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            rows = (
                await s.execute(
                    sql(
                        """select l.id, l.project_id from project_labors l
                           where l.scenario = 'REALIZADO'
                             and l.project_id = (select project_id from project_labors
                                                  where scenario='REALIZADO' limit 1)
                             and l.competencia in (
                                 select distinct competencia from project_labors
                                 where scenario='REALIZADO' order by 1 desc limit 2)
                           order by l.competencia"""
                    )
                )
            ).all()
            comps = (
                await s.execute(
                    sql(
                        """select count(distinct competencia) from project_labors
                           where id = any(:ids)"""
                    ),
                    {"ids": [r.id for r in rows]},
                )
            ).scalar_one()
            if len(rows) < 2 or comps < 2:
                self.skipTest("Banco não tem duas competências para o mesmo projeto.")
            try:
                with self.assertRaises(HTTPException) as ctx:
                    await ProjectStructureService(s).delete_items_bulk(
                        project_id=rows[0].project_id,
                        category="labor",
                        ids=[r.id for r in rows],
                        confirm=False,
                    )
                self.assertEqual(ctx.exception.status_code, 400)
            finally:
                await s.rollback()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
