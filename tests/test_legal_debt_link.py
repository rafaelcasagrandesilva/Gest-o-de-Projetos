"""Jurídico × Endividamento: o pago do acordo vem da dívida vinculada.

- o nome só SUGERE (primeiro nome + mais um em comum; homônimo de primeiro nome não basta);
- vínculo confirmado grava `legal_case_id`/`legal_person_id` na dívida sem renomeá-la;
- o processo vinculado recebe pago/saldo do Endividamento, que a edição manual não sobrescreve;
- desligado sem processo também mostra a situação (quitado/em pagamento).

Os testes com banco trocam `commit` por `flush` e desfazem tudo no final: nada persiste.
"""

from __future__ import annotations

import unittest
from datetime import date
from uuid import uuid4


class NameMatchTests(unittest.TestCase):
    def test_nome_da_divida_com_rotulo_de_acordo_casa_com_o_desligado(self) -> None:
        from app.services.legal_debt_link_service import name_match

        self.assertEqual(
            name_match("CAROLINA DE ABREU - ACORDO RESCISÃO", "Carolina de Abreu Rodrigues"), "ALTA"
        )
        self.assertEqual(
            name_match(
                "PAULO SÉRGIO ALVES DOS SANTOS - ACORDO DE RESCISAO", "Paulo Sergio Alves dos Santos Silva"
            ),
            "ALTA",
        )

    def test_nome_que_a_pessoa_nao_tem_rebaixa_a_confianca(self) -> None:
        from app.services.legal_debt_link_service import name_match

        self.assertEqual(name_match("Pedro Rodrigues Montalvão", "Pedro dos Santos Rodrigues"), "MEDIA")

    def test_so_o_primeiro_nome_nao_e_vinculo(self) -> None:
        """Os falsos positivos do cruzamento por nome: Paulo Sérgio × Paulo Afonso × Paulo Pereira."""
        from app.services.legal_debt_link_service import name_match

        self.assertIsNone(name_match("Paulo Afonso da Silva Arieiro", "Paulo Sergio Alves dos Santos"))
        self.assertIsNone(name_match("Ana Rossi", "Ana Beatriz"))
        self.assertIsNone(name_match("Ana Rossi", "Beatriz Rossi"))

    def test_sobrenome_comum_fica_como_sugestao_media(self) -> None:
        """"Mateus da Silva Souza" × "Mateus Correa de Souza": pode ser outro — nunca vira ALTA."""
        from app.services.legal_debt_link_service import name_match

        self.assertEqual(name_match("Mateus da Silva Souza", "Mateus Correa de Souza"), "MEDIA")

    def test_preposicao_nao_conta_como_nome_em_comum(self) -> None:
        from app.services.legal_debt_link_service import name_match

        self.assertIsNone(name_match("Maria de Souza", "Maria da Conceição"))


class AgreementInstallmentsTests(unittest.TestCase):
    """Formatos reais das "Condições do acordo" cadastradas no Jurídico."""

    def test_formatos_do_juridico(self) -> None:
        from app.services.legal_debt_link_service import parse_agreement_installments as parse

        casos = {
            "3 X 2.333,34": ([2333.34] * 3, None, 7000.02),
            "3X 2.333,34": ([2333.34] * 3, None, 7000.02),
            "2 x 3.700,00 e 1 x 3.600,00": ([3700.0, 3700.0, 3600.0], None, 11000.0),
            "1 X 2.000,00 e 2X 1.700,00": ([2000.0, 1700.0, 1700.0], None, 5400.0),
            "1 X 3250,00 e 4 X 2600,00": ([3250.0] + [2600.0] * 4, None, 13650.0),
            "4 PARCELAS DE 8.500,00 COM VENCIMENTO TODO DIA 30.": ([8500.0] * 4, 30, 34000.0),
        }
        for texto, (valores, dia, total) in casos.items():
            with self.subTest(texto=texto):
                plano = parse(texto)
                self.assertIsNotNone(plano)
                self.assertEqual(plano.values(), valores)
                self.assertEqual(plano.due_day, dia)
                self.assertEqual(plano.total, total)

    def test_texto_sem_parcelas_nao_inventa_cronograma(self) -> None:
        from app.services.legal_debt_link_service import parse_agreement_installments as parse

        self.assertIsNone(parse(None))
        self.assertIsNone(parse("Acordo verbal, aguardando minuta"))


class PaymentSummaryTests(unittest.TestCase):
    def _debt(self, *, paid: float, total: float, settled: bool, month: date | None = None):
        from app.services.legal_debt_link_service import DebtPayment

        return DebtPayment(
            item_id=uuid4(), name="x", case_id=None, person_id=None, total=total, paid=paid,
            pending=round(total - paid, 2), settled=settled, settled_month=month, is_active=True,
        )

    def test_quitado_so_quando_todas_as_dividas_zeraram(self) -> None:
        from app.services.legal_debt_link_service import PaymentSummary

        s = PaymentSummary([self._debt(paid=100, total=100, settled=True, month=date(2026, 8, 1))])
        self.assertEqual(s.status, "QUITADO")
        self.assertEqual(s.settled_month, date(2026, 8, 1))
        s.debts.append(self._debt(paid=10, total=50, settled=False))
        self.assertEqual(s.status, "EM_PAGAMENTO")
        self.assertIsNone(s.settled_month)
        self.assertEqual((s.total, s.paid, s.pending), (150, 110, 40))

    def test_sem_divida_nao_tem_situacao(self) -> None:
        from app.services.legal_debt_link_service import PaymentSummary

        self.assertIsNone(PaymentSummary().status)


class LegalDebtLinkDBTests(unittest.IsolatedAsyncioTestCase):
    async def _session(self):
        from app.database.session import AsyncSessionLocal, engine

        await engine.dispose()
        s = AsyncSessionLocal()

        async def flush_only() -> None:
            await s.flush()

        s.commit = flush_only  # type: ignore[method-assign]
        return s

    async def _fixture(self, s, tag: str):
        from app.models.company_finance import CompanyFinancialItem, CompanyFinancialPayment
        from app.models.legal import LegalCase, LegalCaseStatus, LegalPerson

        pessoa = LegalPerson(full_name=f"Fulana Teste{tag} Silva", is_active=True)
        s.add(pessoa)
        await s.flush()
        caso = LegalCase(
            case_number=f"TESTE-{tag}",
            person_id=pessoa.id,
            status=LegalCaseStatus.ACORDO,
            amount_agreed=3000,
            agreement_terms="3 x 1.000,00",
            amount_paid=None,
        )
        divida = CompanyFinancialItem(
            tipo="endividamento",
            nome=f"FULANA TESTE{tag} - ACORDO RESCISÃO",
            valor_referencia=3000,
            category="Endividamento",
            recurrence="mensal",
            start_date=date(2026, 1, 1),
        )
        s.add_all([caso, divida])
        await s.flush()
        # Mês passado pago: o razão conta o lançamento até hoje.
        s.add(CompanyFinancialPayment(item_id=divida.id, competencia=date(2026, 1, 1), valor=1000))
        await s.flush()
        return pessoa, caso, divida

    async def test_sugere_vincula_e_o_processo_passa_a_mostrar_o_pago(self) -> None:
        from app.models.legal import LegalCase
        from app.services.legal_debt_link_service import PAID_SOURCE_DEBT, LegalDebtLinkService
        from app.services.legal_service import LegalService

        tag = uuid4().hex[:6].upper().replace("0", "A")
        s = await self._session()
        try:
            pessoa, caso, divida = await self._fixture(s, tag)
            svc = LegalDebtLinkService(s)

            sug = [x for x in await svc.suggestions() if x["item_id"] == divida.id]
            self.assertEqual(len(sug), 1)
            self.assertEqual(sug[0]["case_id"], caso.id)
            self.assertEqual(sug[0]["confidence"], "ALTA")
            self.assertTrue(sug[0]["value_matches"])

            await svc.link(item_id=divida.id, case_id=caso.id, person_id=None)
            # Ponteiro: a dívida guarda o processo E o desligado, e não é renomeada.
            self.assertEqual(divida.legal_case_id, caso.id)
            self.assertEqual(divida.legal_person_id, pessoa.id)
            self.assertEqual(divida.nome, f"FULANA TESTE{tag} - ACORDO RESCISÃO")

            await s.refresh(caso)
            self.assertEqual(caso.paid_source, PAID_SOURCE_DEBT)
            summary = svc.by_case(svc.loaded)[caso.id]
            self.assertEqual(float(caso.amount_paid), 1000.0)
            # Saldo = o do motor do Endividamento (com encargos), não "acordo − pago" refeito aqui.
            self.assertEqual(float(caso.amount_pending), summary.pending)
            self.assertGreater(summary.pending, 0)
            self.assertEqual(summary.status, "EM_PAGAMENTO")
            self.assertEqual(svc.by_person(svc.loaded)[pessoa.id].status, "EM_PAGAMENTO")

            # Edição manual do pago é ignorada enquanto houver dívida vinculada.
            await LegalService(s).update_case(caso.id, {"amount_paid": 1.0, "notes": "ok"})
            row = await s.get(LegalCase, caso.id)
            self.assertEqual(float(row.amount_paid), 1000.0)
            self.assertEqual(row.notes, "ok")

            # Vinculada, a dívida não volta como sugestão.
            self.assertFalse([x for x in await svc.suggestions() if x["item_id"] == divida.id])

            # Desvincular devolve o processo ao valor digitado (mantém o último valor).
            await svc.unlink(item_id=divida.id, include_person=True)
            await s.refresh(caso)
            self.assertIsNone(caso.paid_source)
            self.assertIsNone(divida.legal_person_id)
        finally:
            await s.rollback()
            await s.close()

    async def test_descartada_nao_volta_e_desligado_sem_processo_tem_situacao(self) -> None:
        from app.services.legal_debt_link_service import LegalDebtLinkService

        tag = uuid4().hex[:6].upper().replace("0", "B")
        s = await self._session()
        try:
            pessoa, caso, divida = await self._fixture(s, tag)
            svc = LegalDebtLinkService(s)
            await svc.dismiss(item_id=divida.id, case_id=caso.id, person_id=pessoa.id)
            self.assertFalse([x for x in await svc.suggestions() if x["item_id"] == divida.id])

            # Acordo de rescisão sem processo: só o desligado.
            await svc.link(item_id=divida.id, case_id=None, person_id=pessoa.id)
            await svc.sync_cases()
            self.assertNotIn(caso.id, svc.by_case(svc.loaded))
            self.assertEqual(svc.by_person(svc.loaded)[pessoa.id].paid, 1000.0)
        finally:
            await s.rollback()
            await s.close()

    async def test_criar_divida_de_desligado_ja_com_o_processo(self) -> None:
        """Cadastro pelo Endividamento: o processo vai junto e o Jurídico lê o pago dali."""
        from app.services.company_finance_service import CompanyFinanceService
        from app.services.legal_debt_link_service import LegalDebtLinkService

        tag = uuid4().hex[:6].upper().replace("0", "D")
        s = await self._session()
        try:
            pessoa, caso, _divida = await self._fixture(s, tag)
            base = {
                "tipo": "endividamento",
                "nome": None,
                "item_description": None,
                "valor_referencia": 3000.0,
                "cost_center_ref": "ADMINISTRATIVO",
                "legal_person_id": pessoa.id,
                "start_date": date(2026, 9, 1),
            }
            row = await CompanyFinanceService(s).create_item(
                data={**base, "legal_case_id": caso.id}, actor_user_id=None
            )
            self.assertEqual(row.legal_case_id, caso.id)
            svc = LegalDebtLinkService(s)
            await svc.sync_cases()
            self.assertIn(caso.id, svc.by_case(svc.loaded))

            # Processo de OUTRA pessoa é recusado.
            from app.models.legal import LegalPerson

            outra = LegalPerson(full_name=f"Outra {tag}", is_active=True)
            s.add(outra)
            await s.flush()
            with self.assertRaises(ValueError):
                await CompanyFinanceService(s).create_item(
                    data={**base, "legal_person_id": outra.id, "legal_case_id": caso.id},
                    actor_user_id=None,
                )
        finally:
            await s.rollback()
            await s.close()

    async def test_editar_a_estrutura_nao_renomeia_divida_vinculada(self) -> None:
        """A tela do Endividamento reenvia o mesmo vínculo a cada edição: o nome fica."""
        from app.services.company_finance_service import CompanyFinanceService
        from app.services.legal_debt_link_service import LegalDebtLinkService

        tag = uuid4().hex[:6].upper().replace("0", "C")
        s = await self._session()
        try:
            pessoa, _caso, divida = await self._fixture(s, tag)
            await LegalDebtLinkService(s).link(item_id=divida.id, case_id=None, person_id=pessoa.id)
            await CompanyFinanceService(s).update_item(
                item_id=divida.id,
                data={"legal_person_id": pessoa.id, "employee_id": None, "description": "x"},
            )
            self.assertEqual(divida.nome, f"FULANA TESTE{tag} - ACORDO RESCISÃO")
        finally:
            await s.rollback()
            await s.close()


if __name__ == "__main__":
    unittest.main()
