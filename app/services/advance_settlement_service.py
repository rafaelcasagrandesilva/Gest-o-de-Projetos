"""Liquidação de NFs antecipadas — obrigação perante a instituição (grão = participação).

A obrigação é uma **participação** de NF numa operação de antecipação confirmada
(`ReceivableAdvanceBatchItem`) cujo perfil de instituição "empresta contra a NF". Ela é liquidada
por N **movimentações** (1:N), permitindo liquidação parcial e múltiplas origens.

A situação (EM_ABERTO / PARCIALMENTE_LIQUIDADA / VENCIDA / LIQUIDADA) e os totais
(valor_total/valor_liquidado/valor_residual) são SEMPRE derivados aqui no backend — nunca gravados.

Independência do Ledger: este serviço conversa com o Repasse **somente** pela interface
`RepasseLedgerPort` (`credit`/`debit`/`balance`/`reverse_source`), nunca com as tabelas do Ledger.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.advance_institution import AdvanceInstitution
from app.models.advance_repasse_ledger import RepasseLedgerSource
from app.models.advance_settlement_movement import (
    FUNDING_SOURCE_LABELS,
    AdvanceFundingSource,
    AdvanceSettlementMovement,
)
from app.models.project import Project
from app.models.receivable import ReceivableInvoice
from app.models.receivable_advance_batch import (
    CONFIRMED_BATCH_STATUSES,
    ReceivableAdvanceBatch,
    ReceivableAdvanceBatchItem,
)
from app.services.advance_operations import resolve_handler_class
from app.services.advance_repasse_ledger_service import (
    AdvanceRepasseLedgerService,
    RepasseLedgerPort,
)

_CENT = Decimal("0.01")
_TOL = Decimal("0.005")

# Situações derivadas da obrigação (nunca gravadas).
EM_ABERTO = "EM_ABERTO"
PARCIALMENTE_LIQUIDADA = "PARCIALMENTE_LIQUIDADA"
VENCIDA = "VENCIDA"
LIQUIDADA = "LIQUIDADA"


def profile_creates_obligation(profile: str | None) -> bool:
    """Fonte ÚNICA de verdade (Fase 1B): a capacidade vem do handler do perfil, não de uma
    constante. Qualquer instituição nova entra no fluxo apenas ligando o flag no seu handler."""
    return bool(resolve_handler_class(profile).creates_settlement_obligation)


def _money(v: float | Decimal | None) -> Decimal:
    return Decimal(str(v or 0)).quantize(_CENT)


def derive_situacao(*, valor_total: Decimal, valor_liquidado: Decimal, vencimento: date, today: date) -> str:
    """Situação da obrigação. Precedência: LIQUIDADA > VENCIDA > PARCIALMENTE_LIQUIDADA > EM_ABERTO.

    `vencimento` = vencimento da NF (invoice.due_date) — a devolução à instituição é por nota."""
    residual = valor_total - valor_liquidado
    if residual <= _TOL:
        return LIQUIDADA
    if vencimento is not None and vencimento < today:
        return VENCIDA
    if valor_liquidado > _TOL:
        return PARCIALMENTE_LIQUIDADA
    return EM_ABERTO


def origens_resumo(movements: list[AdvanceSettlementMovement]) -> str:
    """Resumo legível das origens ATIVAS, por valor desc. Ex.: 'Repasse + Caixa'."""
    totals: dict[AdvanceFundingSource, Decimal] = {}
    for m in movements:
        if m.reversed_at is not None:
            continue
        totals[m.funding_source] = totals.get(m.funding_source, Decimal("0")) + _money(m.amount)
    ordered = sorted(totals.items(), key=lambda kv: (-kv[1], FUNDING_SOURCE_LABELS.get(kv[0], "")))
    return " + ".join(FUNDING_SOURCE_LABELS.get(fs, fs.value) for fs, _ in ordered)


class AdvanceSettlementService:
    def __init__(self, db: AsyncSession, *, ledger: RepasseLedgerPort | None = None) -> None:
        self.db = db
        # Depende da INTERFACE do Ledger, não das tabelas. Default: implementação concreta.
        self.ledger: RepasseLedgerPort = ledger or AdvanceRepasseLedgerService(db)

    # --- resolução de perfil / instituição ------------------------------------

    async def _obligation_profiles_maps(self) -> tuple[dict[UUID, AdvanceInstitution], dict[str, AdvanceInstitution]]:
        insts = list((await self.db.execute(select(AdvanceInstitution))).scalars().all())
        by_id = {i.id: i for i in insts}
        by_name = {(i.name or "").strip().upper(): i for i in insts}
        return by_id, by_name

    def _resolve_profile(
        self,
        batch: ReceivableAdvanceBatch,
        *,
        by_id: dict[UUID, AdvanceInstitution],
        by_name: dict[str, AdvanceInstitution],
    ) -> tuple[str | None, UUID | None]:
        """Retorna (perfil, institution_id) do lote — por institution_id, com fallback por nome."""
        inst = None
        if batch.institution_id is not None:
            inst = by_id.get(batch.institution_id)
        if inst is None:
            inst = by_name.get((batch.institution or "").strip().upper())
        if inst is not None:
            return (inst.operation_profile or "").strip().upper() or None, inst.id
        # Sem cadastro: usa o texto denormalizado como perfil-guess (ex.: "LEPTA").
        return (batch.institution or "").strip().upper() or None, batch.institution_id

    # --- movimentações por obrigação ------------------------------------------

    async def _movements_for_items(self, item_ids: list[UUID]) -> dict[UUID, list[AdvanceSettlementMovement]]:
        if not item_ids:
            return {}
        rows = list(
            (
                await self.db.execute(
                    select(AdvanceSettlementMovement)
                    .where(AdvanceSettlementMovement.batch_item_id.in_(item_ids))
                    .order_by(AdvanceSettlementMovement.settled_at.asc(), AdvanceSettlementMovement.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        out: dict[UUID, list[AdvanceSettlementMovement]] = {}
        for m in rows:
            out.setdefault(m.batch_item_id, []).append(m)
        return out

    @staticmethod
    def _liquidado(movements: list[AdvanceSettlementMovement]) -> Decimal:
        return sum((_money(m.amount) for m in movements if m.reversed_at is None), Decimal("0.00")).quantize(_CENT)

    def _movement_dict(self, m: AdvanceSettlementMovement) -> dict:
        return {
            "id": m.id,
            "batch_item_id": m.batch_item_id,
            "amount": float(_money(m.amount)),
            "funding_source": m.funding_source.value,
            "settled_at": m.settled_at,
            "observation": m.observation,
            "reversed_at": m.reversed_at,
            "reversal_reason": m.reversal_reason,
            "created_at": m.created_at,
        }

    # --- listagem de obrigações -----------------------------------------------

    async def list_obligations(
        self,
        *,
        today: date | None = None,
        institution_id: UUID | None = None,
        invoice_number: str | None = None,
        sgc_number: int | None = None,
        situacao: str | None = None,
    ) -> list[dict]:
        """Deriva as obrigações (participações) de operações confirmadas de perfil credor.

        Todos os valores e a situação vêm computados daqui — o frontend nunca recalcula.
        """
        today = today or date.today()
        by_id, by_name = await self._obligation_profiles_maps()

        stmt = (
            select(ReceivableAdvanceBatchItem, ReceivableAdvanceBatch, ReceivableInvoice, Project)
            .join(ReceivableAdvanceBatch, ReceivableAdvanceBatch.id == ReceivableAdvanceBatchItem.batch_id)
            .join(ReceivableInvoice, ReceivableInvoice.id == ReceivableAdvanceBatchItem.invoice_id)
            .join(Project, Project.id == ReceivableInvoice.project_id, isouter=True)
            .where(ReceivableAdvanceBatch.status.in_(CONFIRMED_BATCH_STATUSES))
            .order_by(ReceivableAdvanceBatch.repayment_date.asc(), ReceivableAdvanceBatch.created_at.asc())
        )
        rows = list((await self.db.execute(stmt)).all())

        # Filtra por perfil credor e monta a lista de item_ids p/ buscar movimentações em lote.
        selected: list[tuple] = []
        for item, batch, inv, proj in rows:
            profile, inst_id = self._resolve_profile(batch, by_id=by_id, by_name=by_name)
            if not profile_creates_obligation(profile):
                continue
            if institution_id is not None and inst_id != institution_id:
                continue
            selected.append((item, batch, inv, proj, profile, inst_id))

        mv_map = await self._movements_for_items([it.id for it, *_ in selected])

        out: list[dict] = []
        for item, batch, inv, proj, profile, inst_id in selected:
            valor_total = _money(item.advanced_amount)
            # Participações com valor antecipado ZERO (ex.: borderôs legados sem o valor por NF
            # registrado) não representam dívida real perante a instituição — ficam fora da lista.
            if valor_total <= _TOL:
                continue
            movements = mv_map.get(item.id, [])
            valor_liquidado = self._liquidado(movements)
            valor_residual = (valor_total - valor_liquidado).quantize(_CENT)
            # O vencimento da obrigação perante a instituição é o vencimento de CADA NF
            # (invoice.due_date) — não a data da operação/borderô. A devolução à instituição
            # acontece no vencimento da nota, controlada aqui na Liquidação.
            vencimento = inv.due_date
            sit = derive_situacao(
                valor_total=valor_total,
                valor_liquidado=valor_liquidado,
                vencimento=vencimento,
                today=today,
            )
            dias_em_atraso = (
                (today - vencimento).days
                if (sit == VENCIDA and vencimento is not None and vencimento < today)
                else 0
            )
            # Filtros pós-derivação.
            if invoice_number and invoice_number.strip().lower() not in (inv.nf_number or "").lower():
                continue
            if sgc_number is not None and int(batch.sgc_number) != int(sgc_number):
                continue
            if situacao and sit != situacao.strip().upper():
                continue
            out.append(
                {
                    "batch_item_id": item.id,
                    "batch_id": batch.id,
                    "invoice_id": inv.id,
                    "institution_id": inst_id,
                    "institution": batch.institution,
                    "institution_profile": profile,
                    "sgc_number": int(batch.sgc_number),
                    "invoice_number": inv.nf_number,
                    "client_name": inv.client_name,
                    "project_name": (proj.name if proj is not None else None),
                    "valor_total": float(valor_total),
                    "valor_liquidado": float(valor_liquidado),
                    "valor_residual": float(valor_residual),
                    "situacao": sit,
                    "receive_date": batch.receive_date,
                    "vencimento": vencimento,
                    "dias_em_atraso": dias_em_atraso,
                    "origens_resumo": origens_resumo(movements),
                    "movimentacoes": [self._movement_dict(m) for m in movements],
                }
            )
        return out

    async def get_obligation(self, batch_item_id: UUID, *, today: date | None = None) -> dict | None:
        item = await self.db.get(ReceivableAdvanceBatchItem, batch_item_id)
        if item is None:
            return None
        obligations = await self.list_obligations(today=today)
        for o in obligations:
            if o["batch_item_id"] == batch_item_id:
                return o
        return None

    # --- liquidar (add movimentações) -----------------------------------------

    async def add_movements(
        self,
        *,
        batch_item_id: UUID,
        movements: list[dict],
        created_by_id: UUID | None = None,
        today: date | None = None,
    ) -> dict:
        """Registra 1..N movimentações de liquidação (parcial/multi-origem) numa transação.

        Guardas:
          (a) Σ movimentações ativas ≤ valor da obrigação (não sobre-liquidar);
          (b) Σ parcelas SALDO_REPASSE ≤ saldo do Ledger da instituição — bloqueia SÓ o excesso de
              repasse; as demais origens completam a diferença livremente (o Ledger nunca fica negativo).
        Só as parcelas SALDO_REPASSE debitam o Ledger (via interface).
        """
        today = today or date.today()
        if not movements:
            raise ValueError("Informe ao menos uma movimentação de liquidação.")

        item = await self.db.get(ReceivableAdvanceBatchItem, batch_item_id)
        if item is None:
            raise ValueError("Obrigação (participação) não encontrada.")
        batch = await self.db.get(ReceivableAdvanceBatch, item.batch_id)
        if batch is None:
            raise ValueError("Operação da obrigação não encontrada.")
        if batch.status not in CONFIRMED_BATCH_STATUSES:
            raise ValueError("Só é possível liquidar obrigações de operações confirmadas.")

        by_id, by_name = await self._obligation_profiles_maps()
        profile, inst_id = self._resolve_profile(batch, by_id=by_id, by_name=by_name)
        if not profile_creates_obligation(profile):
            raise ValueError("Esta operação não gera obrigação de liquidação.")
        if inst_id is None:
            raise ValueError("Operação sem instituição cadastrada: não é possível liquidar.")

        # Normaliza/valida as parcelas.
        parsed: list[tuple[AdvanceFundingSource, Decimal, date, str | None]] = []
        for m in movements:
            fs = m["funding_source"]
            fs = fs if isinstance(fs, AdvanceFundingSource) else AdvanceFundingSource(str(fs))
            amount = _money(m["amount"])
            if amount <= 0:
                raise ValueError("Cada movimentação deve ter valor positivo.")
            settled_at = m.get("settled_at") or today
            obs = (m.get("observation") or None)
            if fs == AdvanceFundingSource.OUTRA and not obs:
                raise ValueError("Origem 'Outra' exige observação.")
            parsed.append((fs, amount, settled_at, obs))

        # (a) guarda de sobre-liquidação.
        valor_total = _money(item.advanced_amount)
        existing = self._liquidado(await self._movements_for_item(item.id))
        add_sum = sum((a for _fs, a, _d, _o in parsed), Decimal("0.00")).quantize(_CENT)
        if existing + add_sum > valor_total + _TOL:
            disponivel = (valor_total - existing).quantize(_CENT)
            raise ValueError(
                f"Liquidação excede o valor da obrigação. Residual disponível: {disponivel:.2f}."
            )

        # (b) guarda de saldo do repasse (só a parcela SALDO_REPASSE).
        repasse_sum = sum(
            (a for fs, a, _d, _o in parsed if fs == AdvanceFundingSource.SALDO_REPASSE),
            Decimal("0.00"),
        ).quantize(_CENT)
        if repasse_sum > 0:
            saldo = await self.ledger.balance(inst_id)
            if repasse_sum > saldo + _TOL:
                raise ValueError(
                    f"Saldo do Repasse insuficiente. Disponível: {saldo:.2f}; solicitado em Repasse: "
                    f"{repasse_sum:.2f}. Use outra origem para complementar a diferença."
                )

        # Cria as movimentações; parcelas SALDO_REPASSE debitam o Ledger (via interface).
        for fs, amount, settled_at, obs in parsed:
            mv = AdvanceSettlementMovement(
                batch_item_id=item.id,
                batch_id=batch.id,
                invoice_id=item.invoice_id,
                institution_id=inst_id,
                amount=amount,
                funding_source=fs,
                settled_at=settled_at,
                observation=obs,
                created_by_id=created_by_id,
            )
            self.db.add(mv)
            await self.db.flush()
            if fs == AdvanceFundingSource.SALDO_REPASSE:
                await self.ledger.debit(
                    institution_id=inst_id,
                    amount=amount,
                    source_type=RepasseLedgerSource.SETTLEMENT,
                    occurred_at=settled_at,
                    description=f"Liquidação NF {item.invoice_id} — SGC {batch.sgc_number}",
                    source_movement_id=mv.id,
                    created_by_id=created_by_id,
                )
        await self.db.flush()
        return await self.get_obligation(item.id, today=today)  # type: ignore[return-value]

    async def _movements_for_item(self, item_id: UUID) -> list[AdvanceSettlementMovement]:
        return (await self._movements_for_items([item_id])).get(item_id, [])

    # --- estorno de movimentação ----------------------------------------------

    async def reverse_movement(
        self, *, movement_id: UUID, reason: str | None = None, today: date | None = None
    ) -> dict:
        mv = await self.db.get(AdvanceSettlementMovement, movement_id)
        if mv is None:
            raise ValueError("Movimentação não encontrada.")
        if mv.reversed_at is not None:
            raise ValueError("Movimentação já estornada.")
        from datetime import datetime, timezone

        mv.reversed_at = datetime.now(timezone.utc)
        mv.reversal_reason = (reason or None)
        # Estorna o DEBIT correspondente no Ledger (se a origem foi SALDO_REPASSE).
        if mv.funding_source == AdvanceFundingSource.SALDO_REPASSE:
            await self.ledger.reverse_source(source_movement_id=mv.id, reason=reason)
        await self.db.flush()
        return await self.get_obligation(mv.batch_item_id, today=today)  # type: ignore[return-value]

    # --- KPIs -----------------------------------------------------------------

    async def kpis(self, *, today: date | None = None, institution_id: UUID | None = None) -> dict:
        today = today or date.today()
        obligations = await self.list_obligations(today=today, institution_id=institution_id)
        nfs_pendentes = sum(1 for o in obligations if o["situacao"] in (EM_ABERTO, PARCIALMENTE_LIQUIDADA))
        nfs_vencidas = sum(1 for o in obligations if o["situacao"] == VENCIDA)
        valor_total_vencido = float(
            sum((_money(o["valor_residual"]) for o in obligations if o["situacao"] == VENCIDA), Decimal("0.00"))
        )
        total_liquidado = float(
            sum((_money(o["valor_liquidado"]) for o in obligations), Decimal("0.00"))
        )
        # Saldo de repasse por instituição envolvida.
        inst_ids = {o["institution_id"] for o in obligations if o["institution_id"] is not None}
        saldo_total = Decimal("0.00")
        for i in inst_ids:
            saldo_total += await self.ledger.balance(i)
        saldo_repasse = float(saldo_total.quantize(_CENT))
        return {
            "nfs_pendentes": nfs_pendentes,
            "nfs_vencidas": nfs_vencidas,
            "valor_total_vencido": valor_total_vencido,
            "total_liquidado": total_liquidado,
            "saldo_repasse": saldo_repasse,
        }

    # --- Indicadores gerenciais (tomada de decisão) ---------------------------

    async def management_summary(self, *, today: date | None = None, institution_id: UUID | None = None) -> dict:
        """Indicadores gerenciais — todos computados no backend, capability-driven (nunca por
        instituição fixa). O frontend só renderiza."""
        today = today or date.today()
        horizon = today + timedelta(days=30)
        obligations = await self.list_obligations(today=today, institution_id=institution_id)

        valor_ainda_antecipado = Decimal("0.00")  # tudo que ainda devemos (Σ residual)
        valor_vencido = Decimal("0.00")
        valor_a_vencer_30d = Decimal("0.00")
        for o in obligations:
            residual = _money(o["valor_residual"])
            if residual <= _TOL:
                continue
            valor_ainda_antecipado += residual
            if o["situacao"] == VENCIDA:
                valor_vencido += residual
            elif o["vencimento"] is not None and today <= o["vencimento"] <= horizon:
                valor_a_vencer_30d += residual

        # Liquidações ativas: distribuição por origem + tempo médio antecipação→liquidação.
        por_origem: dict[str, Decimal] = {}
        dias_soma = Decimal("0")
        dias_peso = Decimal("0")
        for o in obligations:
            recv = o.get("receive_date")
            for m in o["movimentacoes"]:
                if m["reversed_at"] is not None:
                    continue
                amt = _money(m["amount"])
                fs = m["funding_source"]
                por_origem[fs] = por_origem.get(fs, Decimal("0.00")) + amt
                if recv is not None and m["settled_at"] is not None:
                    dias = Decimal((m["settled_at"] - recv).days)
                    dias_soma += dias * amt
                    dias_peso += amt

        total_liquidado = sum(por_origem.values(), Decimal("0.00")).quantize(_CENT)
        repasse_key = AdvanceFundingSource.SALDO_REPASSE.value
        liquidado_repasse = por_origem.get(repasse_key, Decimal("0.00")).quantize(_CENT)
        liquidado_outras = (total_liquidado - liquidado_repasse).quantize(_CENT)
        tempo_medio = float((dias_soma / dias_peso).quantize(Decimal("0.1"))) if dias_peso > 0 else None

        distribuicao = [
            {
                "funding_source": fs,
                "label": FUNDING_SOURCE_LABELS.get(AdvanceFundingSource(fs), fs),
                "total": float(v.quantize(_CENT)),
                "pct": float((v / total_liquidado * 100).quantize(Decimal("0.1"))) if total_liquidado > 0 else 0.0,
            }
            for fs, v in sorted(por_origem.items(), key=lambda kv: -kv[1])
        ]

        return {
            "valor_ainda_antecipado": float(valor_ainda_antecipado.quantize(_CENT)),
            "valor_vencido": float(valor_vencido.quantize(_CENT)),
            "valor_a_vencer_30d": float(valor_a_vencer_30d.quantize(_CENT)),
            "tempo_medio_liquidacao_dias": tempo_medio,
            "liquidado_repasse": float(liquidado_repasse),
            "liquidado_outras_origens": float(liquidado_outras),
            "total_liquidado": float(total_liquidado),
            "distribuicao_origens": distribuicao,
        }

    # --- Timeline da obrigação (append-only; só exibe a história) -------------

    async def obligation_timeline(self, batch_item_id: UUID, *, today: date | None = None) -> dict:
        """Sequência de eventos derivada dos FATOS (nunca recalcula): Antecipada → Venceu →
        Liquidação parcial → … → Liquidada / Estorno. Ordena a história append-only."""
        today = today or date.today()
        o = await self.get_obligation(batch_item_id, today=today)
        if o is None:
            raise ValueError("Obrigação não encontrada.")
        valor_total = _money(o["valor_total"])
        events: list[dict] = []
        if o.get("receive_date") is not None:
            events.append({"date": o["receive_date"], "order": 0, "tipo": "ANTECIPADA",
                           "label": "Antecipada", "amount": float(valor_total), "origem": None, "estornada": False})
        if o["vencimento"] is not None and o["vencimento"] <= today:
            events.append({"date": o["vencimento"], "order": 1, "tipo": "VENCEU",
                           "label": "Venceu", "amount": None, "origem": None, "estornada": False})
        # Movimentações em ordem cronológica; rótulo parcial/liquidada pelo acumulado ATIVO.
        movs = sorted(o["movimentacoes"], key=lambda m: (str(m["settled_at"]), str(m["created_at"])))
        running = Decimal("0.00")
        for m in movs:
            reversed_ = m["reversed_at"] is not None
            amt = _money(m["amount"])
            origem = FUNDING_SOURCE_LABELS.get(AdvanceFundingSource(m["funding_source"]), m["funding_source"])
            if reversed_:
                label = "Liquidação estornada"
            else:
                running += amt
                label = "Liquidada" if running >= valor_total - _TOL else "Liquidação parcial"
            events.append({"date": m["settled_at"], "order": 2, "tipo": "LIQUIDACAO",
                           "label": label, "amount": float(amt), "origem": origem, "estornada": reversed_})
        events.sort(key=lambda e: (str(e["date"]), e["order"]))
        return {"batch_item_id": batch_item_id, "situacao": o["situacao"], "events": events}

    # --- Históricos de auditoria (append-only, capability-driven) --------------

    async def invoice_history(self, invoice_id: UUID, *, today: date | None = None) -> dict:
        """Todas as obrigações (participações) de uma NF + suas movimentações."""
        obligations = [o for o in await self.list_obligations(today=today) if o["invoice_id"] == invoice_id]
        return {"invoice_id": invoice_id, "obrigacoes": obligations}

    async def batch_history(self, batch_id: UUID, *, today: date | None = None) -> dict:
        """Histórico completo de um borderô: suas obrigações + os lançamentos de repasse do lote."""
        obligations = [o for o in await self.list_obligations(today=today) if o["batch_id"] == batch_id]
        entries = await AdvanceRepasseLedgerService(self.db).entries_for_batch(batch_id)
        repasse = [
            {
                "id": e.id,
                "direction": e.direction.value,
                "amount": float(_money(e.amount)),
                "source_type": e.source_type.value,
                "occurred_at": e.occurred_at,
                "description": e.description,
                "reversed_at": e.reversed_at,
            }
            for e in entries
        ]
        return {"batch_id": batch_id, "obrigacoes": obligations, "repasse": repasse}
