from __future__ import annotations

MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ROWS = 2500
SAMPLE_PREVIEW_ROWS = 5
ANALYZE_SAMPLE_ROWS = 8

LEGACY_HEADER_HINTS = (
    "empresa",
    "fornecedor",
    "data de pagamento",
    "valor",
    "observação",
    "observacao",
    "categoria",
)

REQUIRED_MAPPING_FIELDS = ("name", "cost_center", "due_date", "amount")
OPTIONAL_MAPPING_FIELDS = ("category", "observation")

DEFAULT_CATEGORY = "Importação"
