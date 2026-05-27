"""Compatibilidade: importação de contas a pagar (use app.services.payable_import)."""

from app.services.payable_import import MAX_IMPORT_BYTES, PayableManualImportService

__all__ = ["MAX_IMPORT_BYTES", "PayableManualImportService"]
