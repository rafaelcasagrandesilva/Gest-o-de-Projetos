"""Resultado da Empresa: cascata, IR/CSLL do Lucro Real, agregação e origem dos custos (puro)."""

from __future__ import annotations

import unittest
import uuid
from datetime import date
from types import SimpleNamespace

from app.models.payable_snapshot import PayableSnapshotType
from app.services.company_costs import (
    CompanyCostMonth,
    CostLine,
    line_from_snapshot,
    projected_item_amount,
)
from app.services.company_result_service import aggregate_months, build_month, summarize_lines
from app.services.tax_calc import LUCRO_PRESUMIDO, LUCRO_REAL

AGO = date(2026, 8, 1)
JUN = date(2026, 6, 1)
SETTINGS = SimpleNamespace(tax_rate=0.09)

CONS = {
    "revenue_total": 1_000.0,
    "operational_cost": 500.0,
    "labor_cost": 450.0,
    "vehicle_cost": 30.0,
    "system_cost": 0.0,
    "fixed_operational_cost": 20.0,
    "tax_amount": 90.0,
    "tax_regime": LUCRO_PRESUMIDO,
    "overhead_amount": 999.0,  # NUNCA entra: os indiretos reais substituem o rateio
    "anticipation_amount": 110.0,
    "anticipation_partial": True,
    "total_retention": 100.0,
}


def month(indirect=(), debts=(), projected=False, paid_basis=False):
    costs = CompanyCostMonth(indirect=list(indirect), debts=list(debts), projected=projected, paid_basis=paid_basis)
    return dict(indirect=list(indirect), costs=costs)


def item(**kw):
    base = dict(
        id=uuid.uuid4(), tipo="custo_fixo", nome="Aluguel", category="Custos diversos", employee_id=None,
        employee=None, item_type=None, percentual=None, valor_referencia=300, is_active=True,
        start_date=None, end_date=None, is_monthly_required=False, uses_custom_schedule=False,
        has_renegotiation=False,
    )
    base.update(kw)
    return SimpleNamespace(**base)


class CascadeTests(unittest.TestCase):
    def test_cascata_do_mes(self) -> None:
        row = build_month(
            competencia=AGO,
            cons=CONS,
            settings=SETTINGS,
            **month(
                indirect=[CostLine(None, "Ana", "Colaborador", True, 120.0), CostLine(None, "Aluguel", "Custos diversos", False, 80.0)],
                debts=[CostLine(None, "Banco", "Endividamento", False, 50.0)],
            ),
        )
        self.assertEqual(row["operational_profit"], 300.0)  # 1000 − 500 − 90 − 110 (sem overhead)
        self.assertEqual(row["available_profit"], 200.0)  # − retenção 100
        self.assertEqual((row["indirect_labor_cost"], row["indirect_supplier_cost"]), (120.0, 80.0))
        self.assertEqual(row["profit_tax_amount"], 0.0)  # Presumido: IR/CSLL já estão nos impostos
        self.assertEqual(row["company_result"], -50.0)  # 200 − 200 − 50
        self.assertAlmostEqual(row["coverage"], 200 / 250)
        self.assertAlmostEqual(row["required_margin"], 250 / 1_000)  # indiretos + dívidas ÷ receita
        # Zero a zero: (diretos 500 + indiretos 200 + dívidas 50) ÷ (1 − 30% de impostos/antecipação/retenção)
        self.assertAlmostEqual(row["break_even_revenue"], 750 / 0.7)
        self.assertAlmostEqual(row["revenue_gap"], 750 / 0.7 - 1_000)
        self.assertAlmostEqual(row["tax_rate"], 0.09)

    def test_faturamento_do_zero_a_zero_fecha_o_resultado_em_zero(self) -> None:
        # Refaz a cascata com a receita do ponto de equilíbrio (custos variáveis na mesma taxa).
        row = build_month(competencia=AGO, cons=CONS, settings=SETTINGS,
                          **month(indirect=[CostLine(None, "X", "C", False, 200.0)],
                                  debts=[CostLine(None, "B", "Endividamento", False, 50.0)]))
        be = row["break_even_revenue"]
        ratio = be / 1_000
        cons_be = {**CONS, "revenue_total": be, "tax_amount": 90 * ratio, "anticipation_amount": 110 * ratio,
                   "total_retention": 100 * ratio}
        at_be = build_month(competencia=AGO, cons=cons_be, settings=SETTINGS,
                            **month(indirect=[CostLine(None, "X", "C", False, 200.0)],
                                    debts=[CostLine(None, "B", "Endividamento", False, 50.0)]))
        self.assertAlmostEqual(at_be["company_result"], 0.0, places=6)

    def test_lucro_real_cobra_ir_csll_sobre_o_lucro_e_nada_no_prejuizo(self) -> None:
        cons = {**CONS, "revenue_total": 200_000.0, "operational_cost": 50_000.0, "tax_amount": 10_000.0,
                "anticipation_amount": 10_000.0, "total_retention": 20_000.0, "tax_regime": LUCRO_REAL}
        row = build_month(competencia=AGO, cons=cons, settings=SETTINGS,
                          **month(indirect=[CostLine(None, "Aluguel", "C", False, 30_000.0)]))
        base = 130_000.0 - 30_000.0  # lucro operacional − indiretos
        self.assertAlmostEqual(row["profit_tax_amount"], base * 0.15 + (base - 20_000) * 0.10 + base * 0.09)
        self.assertAlmostEqual(row["company_result"], 110_000.0 - 30_000.0 - row["profit_tax_amount"])
        prejuizo = build_month(competencia=AGO, cons={**cons, "operational_cost": 180_000.0}, settings=SETTINGS,
                               **month(indirect=[CostLine(None, "Aluguel", "C", False, 30_000.0)]))
        self.assertEqual(prejuizo["profit_tax_amount"], 0.0)

    def test_mes_fechado_conta_o_pago_e_separa_o_saldo_em_aberto(self) -> None:
        row = build_month(
            competencia=AGO,
            cons=CONS,
            settings=SETTINGS,
            **month(
                indirect=[CostLine(None, "KLIMA", "Custos diversos", False, 50_000.0, 8_000.0)],
                debts=[CostLine(None, "Banco", "Endividamento", False, 0.0, 3_000.0)],
                paid_basis=True,
            ),
        )
        self.assertEqual((row["indirect_cost"], row["indirect_open_cost"]), (50_000.0, 8_000.0))
        self.assertEqual((row["debt_cost"], row["debt_open_cost"]), (0.0, 3_000.0))
        self.assertEqual(row["company_result"], 200.0 - 50_000.0)
        self.assertTrue(row["paid_basis"])

    def test_resultado_negativo_tambem_tem_faturamento_do_zero_a_zero(self) -> None:
        row = build_month(competencia=AGO, cons={**CONS, "total_retention": 400.0}, settings=SETTINGS,
                          **month(debts=[CostLine(None, "B", "Endividamento", False, 10.0)]))
        self.assertLess(row["available_margin"], 0)
        self.assertAlmostEqual(row["break_even_revenue"], 510 / (1 - 0.6))  # (500 + 10) ÷ (1 − 60%)
        self.assertGreater(row["revenue_gap"], 0)

    def test_sem_receita_nao_ha_zero_a_zero(self) -> None:
        row = build_month(competencia=AGO, cons={**CONS, "revenue_total": 0.0}, settings=SETTINGS, **month())
        self.assertIsNone(row["break_even_revenue"])
        self.assertIsNone(row["required_margin"])

    def test_periodo_recalcula_percentuais_e_marca_regime_misto(self) -> None:
        a = build_month(competencia=JUN, cons=CONS, settings=SETTINGS,
                        **month(indirect=[CostLine(None, "X", "C", False, 100.0, 5.0)], paid_basis=True))
        b = build_month(competencia=AGO, cons={**CONS, "revenue_total": 3_000.0, "anticipation_partial": False,
                                               "tax_regime": LUCRO_REAL}, settings=SETTINGS,
                        **month(indirect=[CostLine(None, "X", "C", False, 100.0)], projected=True))
        total = aggregate_months([a, b])
        self.assertEqual(total["revenue"], 4_000.0)
        self.assertEqual(total["indirect_open_cost"], 5.0)
        self.assertEqual(total["tax_regime"], "MISTO")
        self.assertAlmostEqual(total["available_margin"], total["available_profit"] / 4_000.0)
        self.assertTrue(total["anticipation_partial"] and total["indirect_projected"] and total["paid_basis"])
        self.assertIsNone(total["competencia"])


class ProjectionTests(unittest.TestCase):
    def test_lancamento_digitado_prevalece_inclusive_zero(self) -> None:
        self.assertEqual(projected_item_amount(item(), comp=AGO, entries_sum=450.0, settings=None), 450.0)
        self.assertEqual(projected_item_amount(item(), comp=AGO, entries_sum=0.0, settings=None), 0.0)

    def test_sem_lancamento_usa_referencia_do_item_vigente(self) -> None:
        self.assertEqual(projected_item_amount(item(), comp=AGO, entries_sum=None, settings=None), 300.0)
        self.assertEqual(projected_item_amount(item(end_date=date(2026, 7, 31)), comp=AGO, entries_sum=None, settings=None), 0.0)
        self.assertEqual(projected_item_amount(item(is_active=False), comp=AGO, entries_sum=450.0, settings=None), 0.0)

    def test_antes_do_piso_so_vale_lancamento(self) -> None:
        self.assertEqual(projected_item_amount(item(), comp=JUN, entries_sum=None, settings=None), 0.0)

    def test_endividamento_segue_obrigatorio_e_cronograma(self) -> None:
        divida = dict(tipo="endividamento", valor_referencia=1_000)
        self.assertEqual(projected_item_amount(item(**divida), comp=AGO, entries_sum=None, settings=None), 0.0)
        self.assertEqual(
            projected_item_amount(item(**divida, is_monthly_required=True), comp=AGO, entries_sum=None, settings=None), 1_000.0
        )
        cronograma = item(**divida, uses_custom_schedule=True)
        self.assertEqual(projected_item_amount(cronograma, comp=AGO, entries_sum=None, settings=None), 0.0)
        self.assertEqual(projected_item_amount(cronograma, comp=AGO, entries_sum=250.0, settings=None), 250.0)


class SnapshotClassificationTests(unittest.TestCase):
    def snap(self, **kw):
        base = dict(
            type=PayableSnapshotType.FIXED_COST, origin="FIXED_COST", ref_id=None, amount_final=100, amount_paid=100,
            name="Título", category="Custo Fixo",
        )
        base.update(kw)
        return SimpleNamespace(**base)

    def test_custo_indireto_usa_categoria_e_destino_do_cadastro(self) -> None:
        projeto = uuid.uuid4()
        it = item(category="Combustível", cost_center_project_id=projeto, fleet_allocation=False)
        kind, line = line_from_snapshot(self.snap(ref_id=it.id), items={it.id: it}, components={})
        self.assertEqual((kind, line.category, line.is_labor, line.project_id), ("indirect", "Combustível", False, projeto))

    def test_mes_fechado_usa_o_valor_pago_do_titulo(self) -> None:
        it = item(nome="KLIMA - Consultoria Financeira")
        titulo = self.snap(ref_id=it.id, amount_final=58_000, amount_paid=50_000)
        _, aberto = line_from_snapshot(titulo, items={it.id: it}, components={}, paid_basis=False)
        self.assertEqual((aberto.amount, aberto.open_amount), (58_000.0, 0.0))
        _, fechado = line_from_snapshot(titulo, items={it.id: it}, components={}, paid_basis=True)
        self.assertEqual((fechado.amount, fechado.open_amount), (50_000.0, 8_000.0))

    def test_componente_variavel_de_colaborador_e_mao_de_obra_indireta(self) -> None:
        it = item(employee_id=uuid.uuid4(), category="Colaborador")
        comp = SimpleNamespace(id=uuid.uuid4(), company_financial_item_id=it.id)
        kind, line = line_from_snapshot(self.snap(origin="VARIABLE", ref_id=comp.id), items={it.id: it}, components={comp.id: comp})
        self.assertEqual((kind, line.item_id, line.is_labor), ("indirect", it.id, True))

    def test_endividamento_e_titulos_de_outras_origens(self) -> None:
        kind, line = line_from_snapshot(self.snap(type=PayableSnapshotType.ENDIVIDAMENTO, origin="DEBT", name="Banco X"), items={}, components={})
        self.assertEqual((kind, line.name), ("debt", "Banco X"))
        self.assertIsNone(line_from_snapshot(self.snap(origin="MANUAL"), items={}, components={}))

    def test_lancamento_manual_entra_so_como_foi_classificado(self) -> None:
        def manual(classification):
            return self.snap(
                type=PayableSnapshotType.MANUAL, origin="MANUAL", name="Avulso", category="Advocacia",
                amount_final=500, amount_paid=200, result_classification=classification,
            )

        kind, line = line_from_snapshot(manual("INDIRETO"), items={}, components={}, paid_basis=True)
        self.assertEqual((kind, line.category, line.amount, line.open_amount), ("indirect", "Advocacia", 200.0, 300.0))
        kind, line = line_from_snapshot(manual("ENDIVIDAMENTO"), items={}, components={})
        self.assertEqual((kind, line.category, line.amount), ("debt", "Endividamento", 500.0))
        # Repasse/retenção/bloqueio e não classificado ficam fora; «Custo direto do projeto» não é custo da
        # empresa — entra nos custos diretos pelo projeto vinculado (load_project_payables).
        for fora in ("FORA", "DIRETO", None):
            self.assertIsNone(line_from_snapshot(manual(fora), items={}, components={}))

    def test_resumo_agrupa_por_item_e_ordena(self) -> None:
        a = uuid.uuid4()
        m1 = month(indirect=[CostLine(a, "Ana", "Colaborador", True, 100.0), CostLine(None, "Luz", "Contas", False, 30.0)])
        m2 = month(indirect=[CostLine(a, "Ana", "Colaborador", True, 100.0)], debts=[CostLine(None, "Banco", "Endividamento", False, 10.0)])
        categories, items, debts = summarize_lines([(m1["indirect"], m1["costs"]), (m2["indirect"], m2["costs"])])
        self.assertEqual(categories[0], {"category": "Colaborador", "amount": 200.0})
        self.assertEqual((items[0]["item_id"], items[0]["amount"], items[0]["is_labor"]), (a, 200.0, True))
        self.assertEqual(debts, [{"item_id": None, "name": "Banco", "amount": 10.0}])


if __name__ == "__main__":
    unittest.main()
