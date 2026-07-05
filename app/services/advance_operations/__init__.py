from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.advance_operations.base import BaseOperationHandler
from app.services.advance_operations.daycoval import DaycovalOperationHandler
from app.services.advance_operations.lepta import LeptaOperationHandler

if TYPE_CHECKING:
    from app.services.receivable_advance_batch_service import ReceivableAdvanceBatchService

# Registro perfil → handler. Adicionar nova instituição = cadastrar + registrar aqui.
_HANDLERS: dict[str, type[BaseOperationHandler]] = {
    "LEPTA": LeptaOperationHandler,
    "DAYCOVAL": DaycovalOperationHandler,
}


class AdvanceOperationService:
    """Resolve o Operation Handler de uma operação a partir do perfil da instituição."""

    def __init__(self, service: "ReceivableAdvanceBatchService") -> None:
        self.service = service

    def resolve(self, profile: str | None) -> BaseOperationHandler:
        cls = _HANDLERS.get((profile or "").strip().upper(), BaseOperationHandler)
        return cls(self.service)


__all__ = [
    "AdvanceOperationService",
    "BaseOperationHandler",
    "LeptaOperationHandler",
    "DaycovalOperationHandler",
]
