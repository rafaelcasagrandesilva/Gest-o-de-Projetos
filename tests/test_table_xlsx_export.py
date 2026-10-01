"""Relatórios em formato Tabela do Excel (Folha e Contas a Pagar)."""

from __future__ import annotations

import io
import unittest
from datetime import date

from openpyxl import load_workbook


class TableXlsxBuilderTests(unittest.TestCase):
    def _wb(self):
        from app.services.export.builders import build_table_xlsx_bytes

        raw = build_table_xlsx_bytes(
            headers=["Nome", "Vencimento", "Valor", "Total"],
            rows=[["A", "2026-10-10", 1234.5, 1234.5], ["B", None, None, 10.0]],
            money_columns=frozenset({3, 4}),
            date_columns=frozenset({2}),
            totals={3: "sum", 4: "sum"},
            bold_columns=frozenset({4}),
        )
        return load_workbook(io.BytesIO(raw))

    def test_table_with_filter_aware_totals(self):
        ws = self._wb().active
        table = ws.tables["Tabela1"]
        self.assertEqual(table.ref, "A1:D4")
        self.assertEqual(table.totalsRowCount, 1)
        self.assertEqual(table.autoFilter.ref, "A1:D3")  # total fora do filtro
        self.assertEqual(ws["A4"].value, "Total")
        self.assertEqual(ws["C4"].value, "=SUBTOTAL(109,Tabela1[Valor])")

    def test_numbers_dates_and_layout(self):
        ws = self._wb().active
        self.assertEqual(ws["C2"].value, 1234.5)  # número, não texto "R$ 1.234,50"
        self.assertIn('"R$"', ws["C2"].number_format)
        self.assertEqual(ws["B2"].value.date(), date(2026, 10, 10))
        self.assertEqual(ws.freeze_panes, "B2")
        self.assertFalse(ws.sheet_view.showGridLines)
        self.assertFalse(any(c.alignment.wrap_text for row in ws.iter_rows() for c in row))
        self.assertEqual(ws["A1"].alignment.horizontal, "center")
        self.assertTrue(ws["D2"].font.b)

    def test_cap_report_uses_table(self):
        from app.services.operational_report_export import render_operational_report_bytes

        payload = {"rows": [{"nome": "X", "vencimento": "2026-10-10", "valor_final": 100.0, "saldo": 100.0}]}
        raw, _, _ = render_operational_report_bytes("payables_detailed", payload, "xlsx", None)
        ws = load_workbook(io.BytesIO(raw)).active
        self.assertIn("Tabela1", ws.tables)
        headers = [c.value for c in ws[1]]
        self.assertEqual(ws.cell(row=2, column=headers.index("Valor final") + 1).value, 100.0)


if __name__ == "__main__":
    unittest.main()
