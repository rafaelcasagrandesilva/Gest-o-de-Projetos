from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.receivable import ReceivableInvoice
from app.services.advance_operations.base import BaseOperationHandler, ItemInput
from app.services.payable_snapshot_service import PayableSnapshotService

if TYPE_CHECKING:
    from app.models.receivable_advance_batch import ReceivableAdvanceBatch

BASIS_MANUAL = "MANUAL"


class DaycovalOperationHandler(BaseOperationHandler):
    """Banco Daycoval.

    Toda a lógica do Daycoval vive aqui (regra 1):
    - valor antecipado informado manualmente por NF, pois as taxas variam (regra 2);
    - na confirmação, as NFs são marcadas como RECEBIDAS e saem de vencimento/atraso,
      permanecendo vinculadas ao borderô (regra 3), sem dupla contagem no Dashboard
      (a operação é a fonte única de receita — regra 4);
    - previsto = soma dos antecipados informados; realizado é editável depois e
      coexiste com o previsto, que nunca é sobrescrito (regras 6–9);
    - nenhuma despesa automática é gerada para a diferença previsto×realizado (regra 10).
    """

    profile = "DAYCOVAL"

    def compute_item_advanced_amount(
        self, *, invoice: ReceivableInvoice, basis: str | None, manual_amount: float | None
    ) -> float:
        # Regra 2: valor antecipado é informado manualmente (não calculado da NF).
        return round(float(manual_amount or 0), 2)

    def compute_received_amount(self, *, advanced_amounts: list[float], fallback: float) -> float:
        return round(sum(advanced_amounts), 2)

    async def prepare_draft(self, *, batch: "ReceivableAdvanceBatch", items_input: list[ItemInput]) -> None:
        for _inv, _basis, manual in items_input:
            if manual is None or float(manual) <= 0:
                raise ValueError("Informe o valor antecipado de cada NF (Daycoval).")
        # Persiste a base MANUAL em cada item.
        normalized = [(inv, BASIS_MANUAL, manual) for inv, _basis, manual in items_input]
        await super().prepare_draft(batch=batch, items_input=normalized)
        # Previsto = soma dos antecipados (congelado de fato na confirmação).
        batch.expected_amount = round(float(batch.received_amount or 0), 2)

    async def on_confirm(self, batch: "ReceivableAdvanceBatch", *, log_user: str | None = None) -> None:
        svc = self.service

        # 1. Congela o previsto a partir dos valores informados por NF (regras 6/8/9).
        advanced: list[float] = []
        for item in batch.items or []:
            adv = round(float(item.advanced_amount or 0), 2)
            item.advanced_amount = adv
            advanced.append(adv)
        batch.expected_amount = round(sum(advanced), 2)
        # received_amount (usado pelo Dashboard) = realizado se já informado, senão previsto (regra 7).
        batch.received_amount = (
            round(float(batch.actual_received_amount), 2)
            if batch.actual_received_amount is not None
            else batch.expected_amount
        )

        # 2. Liquida as NFs: marca como RECEBIDAS, fora de vencimento/atraso, sem
        #    dupla contagem no Dashboard (regras 3 e 4). Permanecem vinculadas (regra 11).
        affected = await svc._liquidate_invoices(batch, log_user=log_user)

        # 3. Sem CAP/despesa automática para a diferença previsto×realizado (regra 10).
        await PayableSnapshotService(svc.db).invalidate_months(months=affected)

    async def on_cancel(self, batch: "ReceivableAdvanceBatch", *, log_user: str | None = None) -> set[date]:  # type: ignore[name-defined]
        # Reverte a liquidação das NFs (volta a EMITIDA, reentra em vencimento/atraso).
        return await self.service._revert_invoice_liquidation(batch, log_user=log_user)
