"""Endividamento de ex-colaborador: vínculo com a pessoa do Jurídico.

Um passivo trabalhista é, por definição, com quem já saiu — e essa pessoa quase nunca está no
cadastro operacional de Colaboradores (`legal_persons` e `employees` são cadastros distintos e
praticamente disjuntos). O vínculo é só IDENTIFICAÇÃO: define o nome do item e não entra em
cálculo financeiro nenhum.

Não commita: rollback ao final.
"""

from __future__ import annotations

import unittest
from datetime import date
from uuid import uuid4


class DebtNomeResolutionTests(unittest.TestCase):
    """Resolução do nome — função pura, sem banco."""

    def test_desligado_define_o_nome_do_titulo(self) -> None:
        from app.services.company_finance_service import debt_nome_for

        self.assertEqual(
            debt_nome_for(
                employee_full_name=None,
                legal_person_full_name="Rodrigo de Almeida da Silva",
                nome="rascunho ignorado",
                item_description="Reclamatória",
            ),
            "Rodrigo de Almeida da Silva",
        )

    def test_sem_vinculo_o_nome_digitado_continua_valendo(self) -> None:
        from app.services.company_finance_service import debt_nome_for

        self.assertEqual(
            debt_nome_for(
                employee_full_name=None,
                legal_person_full_name=None,
                nome="Financiamento veículos",
                item_description="Banco X",
            ),
            "Financiamento veículos",
        )

    def test_colaborador_ativo_continua_tendo_precedencia(self) -> None:
        """Garantia de não-regressão: o caminho antigo não mudou de comportamento."""
        from app.services.company_finance_service import debt_nome_for

        self.assertEqual(
            debt_nome_for(
                employee_full_name="Colaborador Ativo",
                nome="ignorado",
                item_description="ignorada",
            ),
            "Colaborador Ativo",
        )


class DebtLegalPersonSchemaTests(unittest.TestCase):
    def test_recusa_colaborador_e_desligado_ao_mesmo_tempo(self) -> None:
        """Dois cadastros de pessoa no mesmo item deixaria o nome ambíguo."""
        from app.schemas.company_finance import CompanyFinancialItemCreate

        with self.assertRaises(ValueError):
            CompanyFinancialItemCreate(
                tipo="endividamento",
                valor_referencia=1000.0,
                cost_center_ref="ADMIN",
                start_date="2026-09-01",
                employee_id=uuid4(),
                legal_person_id=uuid4(),
            )

    def test_desligado_sozinho_dispensa_o_nome_digitado(self) -> None:
        from app.schemas.company_finance import CompanyFinancialItemCreate

        payload = CompanyFinancialItemCreate(
            tipo="endividamento",
            valor_referencia=1000.0,
            cost_center_ref="ADMIN",
            start_date="2026-09-01",
            legal_person_id=uuid4(),
        )
        self.assertIsNotNone(payload.legal_person_id)

    def test_custo_fixo_nao_aceita_vinculo_com_desligado(self) -> None:
        """Custo fixo recorrente não é de quem saiu da empresa — o campo é zerado."""
        from app.schemas.company_finance import CompanyFinancialItemCreate

        payload = CompanyFinancialItemCreate(
            tipo="custo_fixo",
            nome="Aluguel",
            valor_referencia=1000.0,
            cost_center_ref="ADMIN",
            start_date="2026-09-01",
            legal_person_id=uuid4(),
        )
        self.assertIsNone(payload.legal_person_id)


class DebtLegalPersonDBTests(unittest.IsolatedAsyncioTestCase):
    async def test_titulo_criado_para_desligado_recebe_o_nome_da_pessoa(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.models.legal import LegalPerson
        from app.services.company_finance_service import CompanyFinanceService

        await engine.dispose()
        tag = uuid4().hex[:6]

        async with AsyncSessionLocal() as s:
            try:
                pessoa = LegalPerson(
                    full_name=f"Ex-Colaborador {tag}",
                    termination_date=date(2025, 8, 8),
                    is_active=True,
                )
                s.add(pessoa)
                await s.flush()

                row = await CompanyFinanceService(s).create_item(
                    data={
                        "tipo": "endividamento",
                        "nome": None,
                        "item_description": "Reclamatória trabalhista",
                        "valor_referencia": 25_000.0,
                        "cost_center_ref": "ADMINISTRATIVO",
                        "legal_person_id": pessoa.id,
                        "start_date": date(2026, 9, 1),
                    },
                    actor_user_id=None,
                )

                # O nome do título vem do cadastro do Jurídico, não do que foi digitado.
                self.assertEqual(row.nome, f"Ex-Colaborador {tag}")
                self.assertEqual(row.legal_person_id, pessoa.id)
                self.assertIsNone(row.employee_id)
                # O vínculo é só identificação: a base financeira segue o valor informado.
                self.assertEqual(float(row.valor_referencia), 25_000.0)
            finally:
                await s.rollback()

    async def test_busca_de_referencia_nao_devolve_pessoa_desativada(self) -> None:
        """Pessoa retirada da relação de desligados não pode reaparecer como opção."""
        from app.database.session import AsyncSessionLocal, engine
        from app.models.legal import LegalPerson
        from app.services.legal_service import LegalService

        await engine.dispose()
        tag = uuid4().hex[:6]

        async with AsyncSessionLocal() as s:
            try:
                s.add_all(
                    [
                        LegalPerson(full_name=f"Ativo {tag}", is_active=True),
                        LegalPerson(full_name=f"Desativado {tag}", is_active=False),
                    ]
                )
                await s.flush()

                achados = await LegalService(s).search_persons_reference(term=tag, limit=10)
                self.assertEqual([p.full_name for p in achados], [f"Ativo {tag}"])
            finally:
                await s.rollback()


if __name__ == "__main__":
    unittest.main()
