"""Custo Fixo × Premiação/Reembolso (auditoria 01/10/2026) e redação do detalhamento."""

from __future__ import annotations

import inspect
import unittest


class DetalhamentoRedacaoTests(unittest.TestCase):
    """O detalhamento da competência passava INTEIRO para quem não tem Dados sensíveis."""

    def _read(self):
        from app.schemas.company_finance import LancamentosCompetenciaRead

        return LancamentosCompetenciaRead.model_validate(
            {
                "item_id": "x",
                "competencia": "2026-09",
                "lancamentos": [{"id": "e1", "competencia": "2026-09", "valor": 10000.0, "cap_amount_paid": 10000.0}],
                "total": 10000.0,
                "componentes": [{"id": "c1", "tipo": "Reembolso", "valor": 254.26, "cap_amount_paid": 254.26}],
                "componentes_total": 254.26,
            }
        )

    def test_valores_do_detalhamento_sao_redigidos(self):
        from app.api.sensitive import _redact_model

        for resource in ("custo_fixo_item", "debt_item"):
            r = _redact_model(resource, self._read())
            self.assertIsNone(r.total)
            self.assertIsNone(r.componentes_total)
            self.assertIsNone(r.lancamentos[0].valor)
            self.assertIsNone(r.lancamentos[0].cap_amount_paid)
            self.assertIsNone(r.componentes[0].valor)
            self.assertEqual(r.componentes[0].tipo, "Reembolso")  # rótulo continua visível

    def test_reembolso_da_grade_tambem_e_redigido(self):
        from app.api.sensitive import _redact_model
        from app.schemas.company_finance import PagamentoMes

        p = _redact_model(
            "company_finance_payment",
            PagamentoMes(mes="2026-09", valor=10000.0, count=1, componentes_valor=890.61, componentes_count=2),
        )
        self.assertIsNone(p.valor)
        self.assertIsNone(p.componentes_valor)
        self.assertEqual(p.componentes_count, 2)


class ComponentesNoCustoFixoTests(unittest.TestCase):
    def test_reembolso_fica_fora_do_valor_da_grade(self):
        """A grade grava `valor`: somar o reembolso ali o gravaria em dobro como lançamento."""
        from app.services.company_finance_service import CompanyFinanceService

        src = inspect.getsource(CompanyFinanceService._item_to_read)
        self.assertIn("valor=by_month.get(m)", src)
        self.assertIn("componentes_valor=", src)

    def test_pago_do_cap_inclui_titulos_dos_componentes(self):
        from app.services.company_finance_service import CompanyFinanceService

        src = inspect.getsource(CompanyFinanceService._cap_rows_for_competence)
        self.assertIn("PayableOrigin.VARIABLE.value", src)


if __name__ == "__main__":
    unittest.main()
