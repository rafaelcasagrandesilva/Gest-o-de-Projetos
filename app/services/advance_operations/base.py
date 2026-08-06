from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from app.models.receivable_advance_batch import ReceivableAdvanceBatchItem
from app.services.payable_snapshot_service import PayableSnapshotService

if TYPE_CHECKING:  # evita import circular em runtime
    from app.models.receivable import ReceivableInvoice
    from app.models.receivable_advance_batch import ReceivableAdvanceBatch
    from app.services.receivable_advance_batch_service import ReceivableAdvanceBatchService

# Entrada de item na montagem da operação: (NF, base escolhida, valor manual opcional).
ItemInput = tuple["ReceivableInvoice", str | None, float | None]


class BaseOperationHandler:
    """Regras default de uma operação de antecipação.

    Reproduz o comportamento histórico do borderô: ao confirmar, as NFs são
    marcadas como ANTECIPADA e as despesas de deságio/tarifa entram em Contas a
    Pagar. Cada instituição com regras próprias (Lepta, Daycoval) sobrescreve os
    ganchos necessários — concentrando aqui toda a lógica específica, sem `if
    instituição == X` espalhado pelo sistema.

    Ganchos disponíveis para os handlers (sem alterar a infra):
      - compute_item_advanced_amount: valor antecipado de cada NF.
      - compute_received_amount: valor líquido da operação (caixa).
      - prepare_draft: monta os itens e os totais do rascunho.
      - on_confirm / on_cancel: efeitos financeiros (CAP, CAR, atualização de NF).
    """

    profile: str = "DEFAULT"

    # Capacidades declarativas (dirigem o fluxo sem `if instituição == X` espalhado).
    # `creates_settlement_obligation`: a operação cria obrigação de liquidação perante a
    # instituição (aba Liquidação). `has_repasse`: a operação retém repasse (credita o Ledger).
    # Qualquer instituição nova habilita o fluxo apenas ligando estes flags no seu handler —
    # sem tocar no serviço de Liquidação (substitui a constante SETTLEMENT_OBLIGATION_PROFILES).
    creates_settlement_obligation: bool = False
    has_repasse: bool = False

    def __init__(self, service: "ReceivableAdvanceBatchService") -> None:
        self.service = service

    # --- montagem do rascunho -------------------------------------------------

    def compute_item_advanced_amount(
        self, *, invoice: "ReceivableInvoice", basis: str | None, manual_amount: float | None
    ) -> float:
        """Valor antecipado de uma NF. Default: valor bruto."""
        return round(float(invoice.gross_amount or 0), 2)

    def compute_received_amount(self, *, advanced_amounts: list[float], fallback: float) -> float:
        """Valor líquido (caixa) da operação. Default: valor informado manualmente."""
        return round(float(fallback), 2)

    async def prepare_draft(self, *, batch: "ReceivableAdvanceBatch", items_input: list[ItemInput]) -> None:
        """Cria os itens do rascunho e define os totais da operação."""
        advanced: list[float] = []
        for invoice, basis, manual_amount in items_input:
            adv = self.compute_item_advanced_amount(invoice=invoice, basis=basis, manual_amount=manual_amount)
            self.service.db.add(
                ReceivableAdvanceBatchItem(
                    batch_id=batch.id,
                    invoice_id=invoice.id,
                    invoice_amount=round(float(invoice.gross_amount or 0), 2),
                    advance_basis=basis,
                    advanced_amount=adv,
                )
            )
            advanced.append(adv)
        batch.received_amount = self.compute_received_amount(
            advanced_amounts=advanced, fallback=float(batch.received_amount or 0)
        )

    # --- efeitos financeiros --------------------------------------------------

    async def on_confirm(self, batch: "ReceivableAdvanceBatch", *, log_user: str | None = None) -> None:
        """Efetiva a operação (DRAFT → OPEN). Comportamento default herdado por todas."""
        svc = self.service
        affected = await svc._mark_invoices_anticipated(batch, log_user=log_user)
        await svc._ensure_payables_for_batch(
            batch_number=svc._display_code(batch),
            institution=batch.institution,
            receive_date=batch.receive_date,
            repayment_date=batch.repayment_date,
            discount_amount=float(batch.discount_amount or 0),
            fee_amount=float(batch.fee_amount or 0),
            batch_id=batch.id,
        )
        await PayableSnapshotService(svc.db).invalidate_months(months=affected)

    async def on_cancel(self, batch: "ReceivableAdvanceBatch", *, log_user: str | None = None) -> set[date]:
        """Reversão específica da instituição no cancelamento.

        O `cancel_batch` já desassocia NFs e remove as despesas automáticas
        vinculadas ao borderô; este gancho cuida apenas de efeitos extras do
        perfil (ex.: Daycoval reverter a marcação de NFs como recebidas).
        Retorna meses adicionais a invalidar.
        """
        return set()
