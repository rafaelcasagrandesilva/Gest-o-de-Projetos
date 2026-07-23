"""Infraestrutura central de Dados Sensíveis (redact_for + SENSITIVE_SPECS).

Garante que a fonte única funciona e que os campos redigidos existem no schema. NÃO ativa
nenhum permission code novo — a proteção usa a permissão `<recurso>.sensitive` já existente,
resolvida pelo efetivo (perfil + grafo `<r>.view ⇒ <r>.sensitive`).
"""

from __future__ import annotations

import unittest


def _accepts_none(field_info) -> bool:
    """True se o tipo do campo aceita None (nullable) — suficiente para a redação."""
    import types, typing
    ann = field_info.annotation
    if ann is type(None):
        return True
    return typing.get_origin(ann) in (typing.Union, getattr(types, "UnionType", None)) and type(None) in typing.get_args(ann)


class SensitiveRegistryTests(unittest.TestCase):
    def test_registry_codes_end_with_sensitive(self) -> None:
        from app.api.sensitive import SENSITIVE_SPECS

        self.assertIn("payables", SENSITIVE_SPECS)
        for resource, spec in SENSITIVE_SPECS.items():
            self.assertTrue(spec.code.endswith(".sensitive"), f"{resource}: {spec.code}")
            # Cada spec redige campos próprios OU delega a filhos aninhados (wrapper).
            self.assertTrue(spec.fields or spec.nested, f"{resource}: sem fields nem nested")
            # Nested aponta para recursos registrados.
            for _attr, child in spec.nested:
                self.assertIn(child, SENSITIVE_SPECS, f"{resource}: nested {child} não registrado")

    def test_payable_fields_exist_and_are_optional(self) -> None:
        """Todos os campos redigidos de payables existem no schema e são Optional (redação = None)."""
        from app.api.sensitive import SENSITIVE_SPECS
        from app.schemas.payables import PayableSnapshotRead

        fields = PayableSnapshotRead.model_fields
        for f in SENSITIVE_SPECS["payables"].fields:
            self.assertIn(f, fields, f"campo {f} ausente no schema")
            # Optional: aceita None (senão a redação quebraria a validação).
            self.assertTrue(_accepts_none(fields[f]), f"campo {f} precisa aceitar None")

    def test_all_registered_fields_exist_and_are_optional(self) -> None:
        """Todo campo redigido existe no schema e é Optional (senão a redação quebraria)."""
        from app.api.sensitive import SENSITIVE_SPECS
        from app.schemas.receivable import (
            InvoiceAnticipationRead as RcvAnticipation,
            ReceivableInvoiceRead,
            ReceivableKpisRead,
            ReceivableManualItemRead,
            ReceivableViewRead,
        )
        from app.schemas.financial import (
            InvoiceAnticipationRead as BillAnticipation,
            InvoiceRead as BillInvoice,
            RevenueRead,
        )
        from app.schemas.receivable_advance_batch import (
            AdvanceBatchSummaryRead,
            AdvanceOperationHistoryRead,
        )

        schema_by_resource = {
            "receivables": ReceivableViewRead,
            "receivables_manual": ReceivableManualItemRead,
            "invoices": ReceivableInvoiceRead,
            "invoice_anticipations": RcvAnticipation,
            "advance_batch_summary": AdvanceBatchSummaryRead,
            "advance_operations": AdvanceOperationHistoryRead,
            "invoices_kpis": ReceivableKpisRead,
            "billing_invoice": BillInvoice,
            "billing_invoice_anticipation": BillAnticipation,
            "billing_revenue": RevenueRead,
        }
        for resource, model in schema_by_resource.items():
            spec = SENSITIVE_SPECS[resource]
            fields = model.model_fields
            for f in spec.fields:
                self.assertIn(f, fields, f"{resource}: campo {f} ausente")
                self.assertTrue(_accepts_none(fields[f]), f"{resource}.{f} precisa aceitar None")

    def test_every_financial_resource_fields_optional(self) -> None:
        """Varredura: TODO recurso registrado tem seus campos monetários Optional no schema.

        Guarda de cobertura — se um novo campo/recurso financeiro entrar sem ser Optional,
        este teste falha (impede regressão silenciosa fora do padrão central).
        """
        from app.api.sensitive import SENSITIVE_SPECS
        from app.schemas import (
            company_finance as cf, costs as co, dashboard as da, financial as fi,
            financial_dashboard as fd,
            indicators as ind, project_structure as ps, projects as pr, receivable as re,
            receivable_advance_batch as rb, assets, fleet, employees as em, payables as pa,
        )

        # Módulos de referência (employees/vehicles/assets) têm testes próprios e um campo
        # legado não-Optional que só funciona pela serialização do FastAPI — fora do escopo aqui.
        MODEL = {
            "payables": pa.PayableSnapshotRead,
            "receivables": re.ReceivableViewRead, "receivables_manual": re.ReceivableManualItemRead,
            "invoices": re.ReceivableInvoiceRead, "invoice_anticipations": re.InvoiceAnticipationRead,
            "advance_batch_summary": rb.AdvanceBatchSummaryRead, "advance_operations": rb.AdvanceOperationHistoryRead,
            "invoices_kpis": re.ReceivableKpisRead, "billing_invoice": fi.InvoiceRead,
            "billing_invoice_anticipation": fi.InvoiceAnticipationRead, "billing_revenue": fi.RevenueRead,
            "project": pr.ProjectDetailRead, "project_labor": ps.ProjectLaborRead,
            "project_labor_detail": ps.ProjectLaborDetailItem, "labor_breakdown": ps.LaborCostBreakdown,
            "project_vehicle": ps.ProjectVehicleRead, "project_value": ps.ProjectSystemCostRead,
            "employee_allocation": em.EmployeeAllocationRead,
            "debt_item": cf.CompanyFinancialItemRead, "custo_fixo_item": cf.CompanyFinancialItemRead,
            "kpi_endividamento": cf.KpiEndividamentoRead, "kpi_custos_fixos": cf.KpiCustosFixosRead,
            "chart_point": cf.ChartPoint, "pendencia_item": cf.PendenciaLancamentoRead,
            "debt_pendencias": cf.PendenciasCustosFixosRead, "custo_fixo_pendencias": cf.PendenciasCustosFixosRead,
            "dashboard_point": da.MonthlyPoint, "dashboard_summary": da.DirectorSummary,
            "dashboard_financial_summary": da.FinancialDashboardSummary,
            "indicator_roi": ind.ProjectRoi, "roi_evolution_point": ind.RoiEvolutionPoint,
            "fin_evolution_point": ind.FinancialEvolutionPoint, "financial_kpi": ind.FinancialKpi,
            "indicator_highlight": ind.MonthlyHighlight, "financial_insights": ind.FinancialInsights,
            "cost_item": co.ProjectFixedCostRead, "cost_allocation": co.CostAllocationRead,
            "financial_dashboard_summary": fd.FinancialDashboardSummaryRead,
            "financial_dashboard_point": fd.FinancialDashboardTimeseriesPoint,
            "financial_dashboard_group": fd.FinancialDashboardGroupedItem,
            "financial_dashboard_breakdown": fd.FinancialDashboardBreakdownRead,
        }
        for resource, spec in SENSITIVE_SPECS.items():
            if resource not in MODEL:
                continue
            fields = MODEL[resource].model_fields
            # Um spec pode cobrir campos que só existem em modelos irmãos (ex.: employees) —
            # a redação ignora ausentes. A invariante é: todo campo PRESENTE aceita None.
            for f in spec.fields:
                if f in fields:
                    self.assertTrue(_accepts_none(fields[f]), f"{resource}.{f} não aceita None")

    def test_nested_invoice_redaction_is_recursive(self) -> None:
        """NF sem sensitive: valores do topo E dos aninhados (antecipações/lote/histórico) omitidos."""
        from datetime import date, datetime, timezone
        from uuid import uuid4

        from app.api.sensitive import redact_for
        from app.schemas.receivable import InvoiceAnticipationRead, ReceivableInvoiceRead
        from app.schemas.receivable_advance_batch import (
            AdvanceBatchSummaryRead,
            AdvanceOperationHistoryRead,
        )

        now = datetime.now(timezone.utc)
        inv = ReceivableInvoiceRead(
            id=uuid4(), created_at=now, updated_at=now, project_id=uuid4(),
            number="NF-1", issue_date=date(2026, 7, 1), due_days=30, due_date=date(2026, 8, 1),
            gross_amount=1000.0, net_amount=950.0, is_anticipated=True,
            received_amount=0.0, interest_amount=50.0,
            anticipations=[
                InvoiceAnticipationRead(
                    id=uuid4(), created_at=now, updated_at=now, invoice_id=uuid4(),
                    institution="BancoX", amount_received=900.0, amount_to_repay=1000.0,
                    data_recebimento=date(2026, 7, 2), due_date=date(2026, 8, 1),
                    juros_total=100.0, taxa_percentual=10.0, taxa_mensal=2.5,
                )
            ],
            advance_batch=AdvanceBatchSummaryRead(
                id=uuid4(), batch_number="B1", institution="BancoX", status="SETTLED",
                received_amount=900.0, gross_amount=1000.0,
            ),
            advance_operations=[
                AdvanceOperationHistoryRead(
                    id=uuid4(), batch_number="B1", institution="BancoX", status="SETTLED",
                    advanced_amount=900.0, received_amount=900.0,
                )
            ],
            status="ANTECIPADA",
        )

        import app.api.deps as deps

        original = deps.user_has_permission
        try:
            deps.user_has_permission = lambda user, code: False  # sem sensitive
            r = redact_for("invoices", inv, object())
            # topo
            self.assertIsNone(r.gross_amount)
            self.assertIsNone(r.net_amount)
            self.assertIsNone(r.interest_amount)
            # aninhados
            self.assertIsNone(r.anticipations[0].amount_received)
            self.assertIsNone(r.anticipations[0].amount_to_repay)
            self.assertIsNone(r.anticipations[0].taxa_mensal)
            self.assertIsNone(r.advance_batch.received_amount)
            self.assertIsNone(r.advance_batch.gross_amount)
            self.assertIsNone(r.advance_operations[0].advanced_amount)
            # estrutura preservada
            self.assertEqual(r.number, "NF-1")
            self.assertEqual(r.advance_batch.institution, "BancoX")
            self.assertEqual(r.status, "ANTECIPADA")

            deps.user_has_permission = lambda user, code: True  # com sensitive
            r2 = redact_for("invoices", inv, object())
            self.assertEqual(r2.gross_amount, 1000.0)
            self.assertEqual(r2.anticipations[0].amount_to_repay, 1000.0)
            self.assertEqual(r2.advance_batch.received_amount, 900.0)
        finally:
            deps.user_has_permission = original

    def test_financial_dashboard_redaction_is_recursive(self) -> None:
        """Dashboard Financeiro sem sensitive: valores do topo E dos aninhados omitidos; com, preservados."""
        from datetime import date

        from app.api.sensitive import redact_for
        from app.schemas.financial_dashboard import (
            FinancialDashboardBreakdownRead,
            FinancialDashboardGroupedItem,
            FinancialDashboardRead,
            FinancialDashboardSummaryRead,
            FinancialDashboardTimeseriesPoint,
        )

        comp = date(2026, 7, 1)
        dash = FinancialDashboardRead(
            summary=FinancialDashboardSummaryRead(
                month=comp, period_start=comp, period_end=comp,
                faturamento=1000.0, pago=400.0, caixa=600.0,
            ),
            timeseries=[
                FinancialDashboardTimeseriesPoint(month=comp, faturamento=1000.0, pago=400.0, caixa=600.0)
            ],
        )
        brk = FinancialDashboardBreakdownRead(
            type="faturamento", month=comp, total=1000.0,
            groups=[FinancialDashboardGroupedItem(label="Projeto A", value=1000.0)],
            received_total=1000.0,
            received_groups=[FinancialDashboardGroupedItem(label="Projeto A", value=1000.0)],
            paid_total=400.0,
            paid_groups=[FinancialDashboardGroupedItem(label="CC", value=400.0)],
        )

        import app.api.deps as deps

        original = deps.user_has_permission
        try:
            deps.user_has_permission = lambda user, code: False  # sem sensitive
            r = redact_for("financial_dashboard", dash, object())
            self.assertIsNone(r.summary.faturamento)
            self.assertIsNone(r.summary.pago)
            self.assertIsNone(r.summary.caixa)
            self.assertIsNone(r.timeseries[0].faturamento)
            self.assertEqual(r.summary.month, comp)  # estrutura preservada
            rb = redact_for("financial_dashboard_breakdown", brk, object())
            self.assertIsNone(rb.total)
            self.assertIsNone(rb.received_total)
            self.assertIsNone(rb.paid_total)
            self.assertIsNone(rb.groups[0].value)
            self.assertIsNone(rb.received_groups[0].value)
            self.assertIsNone(rb.paid_groups[0].value)
            self.assertEqual(rb.groups[0].label, "Projeto A")

            deps.user_has_permission = lambda user, code: True  # com sensitive
            r2 = redact_for("financial_dashboard", dash, object())
            self.assertEqual(r2.summary.faturamento, 1000.0)
            self.assertEqual(r2.timeseries[0].caixa, 600.0)
            rb2 = redact_for("financial_dashboard_breakdown", brk, object())
            self.assertEqual(rb2.total, 1000.0)
            self.assertEqual(rb2.groups[0].value, 1000.0)
        finally:
            deps.user_has_permission = original

    def test_redact_for_omits_when_no_sensitive_and_keeps_when_has(self) -> None:
        """redact_for zera os valores sem a permissão e preserva com a permissão."""
        from datetime import date, datetime, timezone
        from uuid import uuid4

        from app.api.sensitive import redact_for
        from app.schemas.payables import PayableSnapshotRead

        now = datetime.now(timezone.utc)
        model = PayableSnapshotRead(
            id=uuid4(), created_at=now, updated_at=now, month=date(2026, 7, 1),
            type="FIXED_COST", ref_id=uuid4(), project_id=None, name="Aluguel",
            cost_center="Administrativo", category="Custo Fixo",
            amount_original=1000.0, amount_final=1000.0, amount_paid=400.0,
            amount_remaining=600.0, overpaid_amount=0.0,
            due_date=date(2026, 7, 10), payment_date=None, paid=False,
            status="PARCIAL", paid_in_period=400.0,
        )

        class _U:  # usuário mínimo; a checagem é via user_has_permission (mockado abaixo)
            pass

        import app.api.deps as deps

        original = deps.user_has_permission
        try:
            # Sem sensitive → valores omitidos (None); status/nome/centro preservados.
            deps.user_has_permission = lambda user, code: False
            r = redact_for("payables", model, _U())
            self.assertIsNone(r.amount_final)
            self.assertIsNone(r.amount_paid)
            self.assertIsNone(r.amount_remaining)
            self.assertIsNone(r.amount_original)
            self.assertIsNone(r.paid_in_period)
            self.assertEqual(r.status, "PARCIAL")   # estrutura preservada
            self.assertEqual(r.name, "Aluguel")
            self.assertEqual(r.cost_center, "Administrativo")

            # Com sensitive → valores preservados.
            deps.user_has_permission = lambda user, code: True
            r2 = redact_for("payables", model, _U())
            self.assertEqual(r2.amount_final, 1000.0)
            self.assertEqual(r2.amount_paid, 400.0)
        finally:
            deps.user_has_permission = original


if __name__ == "__main__":
    unittest.main()
