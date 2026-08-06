from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.receivable import ReceivableInvoice
from app.services.advance_operations.base import BaseOperationHandler, ItemInput
from app.services.payable_snapshot_service import PayableSnapshotService
from app.utils.date_utils import normalize_competencia

if TYPE_CHECKING:
    from app.models.receivable_advance_batch import ReceivableAdvanceBatch

# Bases de antecipação suportadas pela Lepta.
BASIS_GROSS = "BRUTO"
BASIS_NET = "LIQUIDO"
BASIS_NET_MINUS_10 = "LIQUIDO_MENOS_10"
LEPTA_BASES = (BASIS_GROSS, BASIS_NET, BASIS_NET_MINUS_10)

REPASSE_RATE = 0.07  # 7% do ANTECIPADO da operação (= "Nominal"/"Total Bruto" do borderô)


class LeptaOperationHandler(BaseOperationHandler):
    """Lepta Multissetorial.

    Toda a lógica da Lepta vive aqui (regra 1):
    - valor antecipado por NF conforme a base escolhida (Bruto / Líquido / Líquido−10%);
    - valor líquido creditado = soma dos antecipados − deságio − tarifas;
    - na confirmação a operação gera até três obrigações no Contas a Pagar, todas com
      competência/vencimento na DATA DE RECEBIMENTO e vinculadas via ref_id=batch.id:
        • Deságio (discount_amount);
        • Tarifas bancárias (fee_amount);
        • Repasse não apropriado = 7% do BRUTO da operação — obrigação ÚNICA da operação
          (não das NFs; independente de quantidade/vencimentos/competências).
    """

    profile = "LEPTA"

    def compute_item_advanced_amount(
        self, *, invoice: ReceivableInvoice, basis: str | None, manual_amount: float | None
    ) -> float:
        gross = float(invoice.gross_amount or 0)
        net = float(invoice.net_amount or 0)
        if basis == BASIS_NET:
            return round(net, 2)
        if basis == BASIS_NET_MINUS_10:
            # Líquido − retenção de 10% sobre o BRUTO da NF (a retenção incide no bruto,
            # não no líquido): LiquidoDescontado = Liquido − (Bruto × 0,10).
            return round(net - gross * 0.10, 2)
        # BRUTO (default seguro).
        return round(gross, 2)

    def compute_received_amount(self, *, advanced_amounts: list[float], fallback: float) -> float:
        # Regra 3: soma dos valores efetivamente escolhidos por NF (nunca um cálculo global).
        return round(sum(advanced_amounts), 2)

    @staticmethod
    def _net_received(advanced_sum: float, batch: "ReceivableAdvanceBatch") -> float:
        """Líquido creditado na conta = soma dos antecipados − deságio − tarifas.

        Esse líquido alimenta Dashboard/CAR/caixa (não alterado nesta etapa). Deságio,
        tarifas e repasse também aparecem como obrigações no Contas a Pagar (ver
        on_confirm) — a dupla representação do custo financeiro é intencional nesta
        etapa e será validada com o financeiro antes de eventual refinamento.
        """
        disc = float(batch.discount_amount or 0)
        fee = float(batch.fee_amount or 0)
        return round(advanced_sum - disc - fee, 2)

    async def prepare_draft(self, *, batch: "ReceivableAdvanceBatch", items_input: list[ItemInput]) -> None:
        await super().prepare_draft(batch=batch, items_input=items_input)
        # Líquido previsto = soma dos antecipados − deságio − tarifas (creditado na conta).
        batch.received_amount = self._net_received(float(batch.received_amount or 0), batch)
        # Pré-visualização do repasse no rascunho (congelado de fato na confirmação).
        if batch.repasse_enabled:
            gross_sum = sum(float(inv.gross_amount or 0) for inv, _b, _m in items_input)
            batch.repasse_amount = round(gross_sum * REPASSE_RATE, 2)
        else:
            batch.repasse_amount = None

    async def on_confirm(self, batch: "ReceivableAdvanceBatch", *, log_user: str | None = None) -> None:
        svc = self.service

        # 1. Congela o valor antecipado de cada NF a partir da base persistida (regra 2),
        #    e recalcula o líquido da operação (regra 3).
        advanced: list[float] = []
        for item in batch.items or []:
            inv = item.invoice or await svc.db.get(ReceivableInvoice, item.invoice_id)
            adv = self.compute_item_advanced_amount(
                invoice=inv, basis=item.advance_basis, manual_amount=float(item.advanced_amount or 0)
            )
            item.advanced_amount = adv
            advanced.append(adv)
        advanced_total = round(sum(advanced), 2)
        # Líquido creditado = soma dos antecipados − deságio − tarifas (congelado).
        batch.received_amount = self._net_received(advanced_total, batch)

        # 2. Repasse = 7% do ANTECIPADO da operação (soma dos valores antecipados das NFs), que é
        #    exatamente o "Nominal"/"Total Bruto" do borderô da LEPTA — validado nos borderôs reais.
        #    O antecipado já reflete a BASE escolhida por NF (Bruto/Líquido/Líquido-10%), que é o
        #    valor que a LEPTA usou como Nominal; assim a regra vale para operações com bases
        #    diferentes (ex.: #11417 base Bruto → 30.100; #11554 base Líquido → 12.323,99).
        batch.repasse_amount = round(advanced_total * REPASSE_RATE, 2) if batch.repasse_enabled else None

        # 3. Marca as NFs como ANTECIPADA (comportamento comum).
        affected = await svc._mark_invoices_anticipated(batch, log_user=log_user)

        # 4. Obrigações financeiras da operação no Contas a Pagar — todas com
        #    competência/vencimento = DATA DE RECEBIMENTO e ref_id=batch.id (removidas
        #    automaticamente no cancelamento por ref_id, como os demais efeitos).
        comp = normalize_competencia(batch.receive_date)
        display = svc._display_code(batch)  # número interno do SGC
        discount = round(float(batch.discount_amount or 0), 2)
        fee = round(float(batch.fee_amount or 0), 2)

        # Nomes curtos para a coluna Nome (largura fixa); o nome completo vai no tooltip.
        if discount > 0.005:
            await svc.add_operation_payable_line(
                batch=batch,
                month=batch.receive_date,
                name=f"Deságio • SGC {display}",
                full_name=f"Deságio - Operação SGC {display}",
                amount=discount,
                due_date=batch.receive_date,
            )
        if fee > 0.005:
            await svc.add_operation_payable_line(
                batch=batch,
                month=batch.receive_date,
                name=f"Tarifas • SGC {display}",
                full_name=f"Tarifas bancárias - Operação SGC {display}",
                amount=fee,
                due_date=batch.receive_date,
            )
        if batch.repasse_enabled and batch.repasse_amount and batch.repasse_amount > 0.005:
            await svc.add_operation_payable_line(
                batch=batch,
                month=batch.receive_date,
                name=f"Repasse não apropriado • SGC {display}",
                full_name=f"Repasse não apropriado - Operação SGC {display}",
                amount=round(float(batch.repasse_amount), 2),
                due_date=batch.receive_date,
            )
        affected.add(comp)

        await PayableSnapshotService(svc.db).invalidate_months(months=affected)
