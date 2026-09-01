"""Consumo do contrato: só NF FATURADA conta.

Regra do negócio definida em 01/09/2026. É o tipo de regra que quebra em silêncio quando alguém
mexe no filtro meses depois — e o número aparece inflado no painel da diretoria sem ninguém
perceber. Por isso o teste trava os quatro casos que compõem a conta.

Não commita: rollback ao final.
"""

from __future__ import annotations

import unittest
from datetime import date
from uuid import uuid4


class ContractConsumptionDBTests(unittest.IsolatedAsyncioTestCase):
    async def test_somente_nf_faturada_entra_no_consumo(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.models.project import Project
        from app.models.project_contract import ProjectContractAdditive
        from app.models.receivable import ReceivableInvoice
        from app.schemas.projects import ProjectRead
        from app.services.projects_service import ProjectsService

        await engine.dispose()
        tag = uuid4().hex[:6]

        async with AsyncSessionLocal() as s:
            try:
                proj = Project(name=f"Contrato {tag}", contract_value=1000.0, is_active=True)
                s.add(proj)
                await s.flush()

                # Aditivo entra na BASE: o contrato cresce com ele.
                s.add(ProjectContractAdditive(project_id=proj.id, additive_value=200.0))

                def nf(numero: str, valor: float, *, oficial: bool, status: str) -> ReceivableInvoice:
                    return ReceivableInvoice(
                        project_id=proj.id,
                        nf_number=f"{tag}-{numero}",
                        gross_amount=valor,
                        net_amount=valor,
                        is_official=oficial,
                        invoice_status=status,
                        issue_date=date(2026, 1, 10),
                        due_days=30,
                        due_date=date(2026, 2, 9),
                    )

                s.add_all(
                    [
                        nf("1", 100.0, oficial=True, status="EMITIDA"),      # conta
                        nf("2", 50.0, oficial=True, status="ANTECIPADA"),    # conta: antecipar não desfaz o faturamento
                        nf("3", 900.0, oficial=False, status="EMITIDA"),     # NÃO conta: pré-faturada
                        nf("4", 400.0, oficial=True, status="CANCELADA"),    # NÃO conta: cancelada
                    ]
                )
                await s.flush()

                numeros = (await ProjectsService(s).contract_consumption_map([proj.id]))[proj.id]
                read = ProjectRead.model_validate(proj)
                read.additive_value_total = numeros.get("additive_value_total", 0.0)
                read.invoiced_total = numeros.get("invoiced_total", 0.0)

                self.assertEqual(read.contract_total_value, 1200.0)  # 1000 + 200 de aditivo
                self.assertEqual(read.invoiced_total, 150.0)         # 100 + 50, e mais nada
                self.assertEqual(read.contract_balance, 1050.0)
                self.assertEqual(read.contract_consumed_pct, 12.5)
            finally:
                await s.rollback()

    async def test_sem_valor_de_contrato_nao_inventa_percentual(self) -> None:
        """Contrato sem valor cadastrado → percentual nulo, para a tela dizer 'não informado'."""
        from app.schemas.projects import ProjectRead

        read = ProjectRead.model_validate(
            {
                "id": uuid4(),
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "name": "Sem contrato",
                "contract_value": None,
            }
        )
        read.invoiced_total = 5000.0

        self.assertIsNone(read.contract_total_value)
        self.assertIsNone(read.contract_consumed_pct)
        self.assertIsNone(read.contract_balance)

    async def test_sem_dados_sensiveis_o_percentual_tambem_some(self) -> None:
        """A redação zera só campos DECLARADOS — campo calculado ela não alcança.

        Sem esta garantia, quem não tem Dados Sensíveis não veria os valores, mas veria o
        percentual do contrato: o número mais revelador dos três.
        """
        from app.api.sensitive import _redact_model
        from app.schemas.projects import ProjectRead

        read = ProjectRead.model_validate(
            {
                "id": uuid4(),
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "name": "Com contrato",
                "contract_value": 1000.0,
            }
        )
        read.additive_value_total = 200.0
        read.invoiced_total = 150.0
        self.assertEqual(read.contract_consumed_pct, 12.5)  # antes da redação, o número existe

        redigido = _redact_model("project", read)
        self.assertIsNone(redigido.invoiced_total)
        self.assertIsNone(redigido.contract_total_value)
        self.assertIsNone(redigido.contract_balance)
        self.assertIsNone(redigido.contract_consumed_pct)


if __name__ == "__main__":
    unittest.main()
