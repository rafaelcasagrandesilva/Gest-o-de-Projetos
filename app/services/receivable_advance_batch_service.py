from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import MissingGreenlet

from app.models.project import Project
from app.models.advance_institution import AdvanceInstitution
from app.models.receivable import ReceivableInvoice, ReceivableInvoiceAnticipation
from app.models.receivable_advance_batch import (
    ReceivableAdvanceBatch,
    ReceivableAdvanceBatchItem,
    ReceivableAdvanceBatchStatus,
)
from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
from app.schemas.receivable import CENT_TOL, derive_invoice_status
from app.services.advance_operations import AdvanceOperationService
from app.services.payable_snapshot_service import PayableSnapshotService
from app.services.receivable_service import ReceivableService, get_affected_months
from app.utils.dashboard_inclusion import apply_dashboard_inclusion_change, append_observation_line
from app.utils.date_utils import normalize_competencia


def _money(v: float | Decimal) -> Decimal:
    return Decimal(str(round(float(v), 2)))


def _next_batch_number(existing: list[str], *, year: int) -> str:
    prefix = f"BT-{year}-"
    max_seq = 0
    for num in existing:
        if not num.startswith(prefix):
            continue
        tail = num[len(prefix) :]
        try:
            max_seq = max(max_seq, int(tail))
        except ValueError:
            continue
    return f"{prefix}{max_seq + 1:04d}"


_BATCH_DISCOUNT_SUFFIX = " — Deságio"
_BATCH_FEE_SUFFIX = " — Tarifas bancárias"


def _batch_payable_observation(operation_tag: str) -> str:
    return f"Operação={operation_tag}"


def _is_bordero_operation_payable(row: PayableSnapshot, *, operation_tag: str) -> bool:
    """Linhas de deságio/tarifa criadas por borderô (MANUAL atual ou ANTECIPACAO legado)."""
    obs = str(getattr(row, "observation", "") or "")
    if _batch_payable_observation(operation_tag) not in obs:
        return False
    name = str(getattr(row, "name", "") or "")
    return _BATCH_DISCOUNT_SUFFIX in name or _BATCH_FEE_SUFFIX in name


def _row_belongs_to_batch(row: PayableSnapshot, *, batch_id: UUID, operation_tag: str) -> bool:
    """Linha de Contas a Pagar pertencente à operação.

    Detecta por `ref_id == batch_id` (lançamentos novos: deságio/tarifa/repasse,
    todos vinculados) e, como fallback, pelo padrão legado de observação+nome
    (linhas antigas com ref_id aleatório).
    """
    if getattr(row, "ref_id", None) == batch_id:
        return True
    return _is_bordero_operation_payable(row, operation_tag=operation_tag)


def _op_display_code(
    *,
    batch_number: str,
    operation_code: str | None,
    batch_id: UUID | None = None,
    sgc_number: int | None = None,
) -> str:
    """Código exibível da operação.

    Preferir o número interno do SGC (identificador operacional oficial). Mantém
    fallbacks determinísticos para robustez (operation_code / batch_number / id).
    """
    if sgc_number is not None:
        return str(sgc_number)
    code = (operation_code or "").strip()
    if code:
        return code
    if batch_number:
        return batch_number
    if batch_id:
        return f"ANTECIPACAO-{str(batch_id)[:8]}"
    return "ANTECIPACAO"


class ReceivableAdvanceBatchService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _invoice_in_active_batch(self, invoice_id: UUID) -> ReceivableAdvanceBatch | None:
        stmt = (
            select(ReceivableAdvanceBatch)
            .join(ReceivableAdvanceBatchItem, ReceivableAdvanceBatchItem.batch_id == ReceivableAdvanceBatch.id)
            .where(
                ReceivableAdvanceBatchItem.invoice_id == invoice_id,
                ReceivableAdvanceBatch.status.in_(
                    [ReceivableAdvanceBatchStatus.DRAFT, ReceivableAdvanceBatchStatus.OPEN]
                ),
            )
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _validate_invoice_eligible(self, inv: ReceivableInvoice) -> None:
        if inv.invoice_status == "CANCELADA":
            raise ValueError(f"NF {inv.nf_number}: cancelada não pode entrar no borderô.")
        recv = float(inv.received_amount or 0)
        net = float(inv.net_amount or 0)
        if recv >= net - CENT_TOL:
            raise ValueError(f"NF {inv.nf_number}: já recebida não pode entrar no borderô.")
        ants = (
            await self.db.execute(
                select(func.count())
                .select_from(ReceivableInvoiceAnticipation)
                .where(ReceivableInvoiceAnticipation.invoice_id == inv.id)
            )
        ).scalar_one()
        if int(ants or 0) > 0:
            raise ValueError(f"NF {inv.nf_number}: já possui antecipação individual.")
        if inv.is_anticipated and inv.advance_batch_id is None:
            raise ValueError(f"NF {inv.nf_number}: já está marcada como antecipada.")
        active = await self._invoice_in_active_batch(inv.id)
        if active is not None:
            raise ValueError(
                f"NF {inv.nf_number}: já está no borderô ativo {active.batch_number}."
            )

    async def list_eligible_invoices(
        self,
        *,
        project_ids: list[UUID] | None,
        search: str | None = None,
        limit: int = 500,
    ) -> list[ReceivableInvoice]:
        active_invoice_ids = select(ReceivableAdvanceBatchItem.invoice_id).join(
            ReceivableAdvanceBatch, ReceivableAdvanceBatch.id == ReceivableAdvanceBatchItem.batch_id
        ).where(
            ReceivableAdvanceBatch.status.in_(
                [ReceivableAdvanceBatchStatus.DRAFT, ReceivableAdvanceBatchStatus.OPEN]
            )
        )

        has_individual_ant = select(ReceivableInvoiceAnticipation.invoice_id).distinct()

        stmt = (
            select(ReceivableInvoice)
            .options(selectinload(ReceivableInvoice.project))
            .join(Project, Project.id == ReceivableInvoice.project_id)
            .where(
                ReceivableInvoice.invoice_status != "CANCELADA",
                ReceivableInvoice.received_amount < ReceivableInvoice.net_amount - CENT_TOL,
                ReceivableInvoice.id.not_in(has_individual_ant),
                ReceivableInvoice.id.not_in(active_invoice_ids),
                or_(ReceivableInvoice.is_anticipated.is_(False), ReceivableInvoice.advance_batch_id.is_(None)),
            )
            .order_by(ReceivableInvoice.due_date.asc(), ReceivableInvoice.nf_number.asc())
            .limit(limit)
        )
        if project_ids is not None:
            stmt = stmt.where(ReceivableInvoice.project_id.in_(project_ids))

        q = (search or "").strip().lower()
        if q:
            stmt = stmt.where(
                or_(
                    func.lower(ReceivableInvoice.nf_number).contains(q),
                    func.lower(func.coalesce(ReceivableInvoice.client_name, "")).contains(q),
                    func.lower(Project.name).contains(q),
                )
            )

        return list((await self.db.execute(stmt)).scalars().unique().all())

    async def get_batch(self, batch_id: UUID) -> ReceivableAdvanceBatch | None:
        stmt = (
            select(ReceivableAdvanceBatch)
            .where(ReceivableAdvanceBatch.id == batch_id)
            .options(
                selectinload(ReceivableAdvanceBatch.items).selectinload(ReceivableAdvanceBatchItem.invoice).selectinload(
                    ReceivableInvoice.project
                ),
                selectinload(ReceivableAdvanceBatch.institution_ref),
            )
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_batches(self, *, limit: int = 100) -> list[ReceivableAdvanceBatch]:
        stmt = (
            select(ReceivableAdvanceBatch)
            .options(
                selectinload(ReceivableAdvanceBatch.items)
                .selectinload(ReceivableAdvanceBatchItem.invoice)
                .selectinload(ReceivableInvoice.project),
                selectinload(ReceivableAdvanceBatch.institution_ref),
            )
            .order_by(ReceivableAdvanceBatch.created_at.desc())
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().unique().all())

    # Chave fixa de advisory lock para serializar a alocação do número do SGC.
    _SGC_LOCK_KEY = 0x5347_4E42  # "SGNB"

    async def _allocate_sgc_number(self) -> int:
        """Aloca o próximo número interno do SGC (sequência global 1, 2, 3, …).

        Serializa via advisory lock transacional para evitar colisões sob
        concorrência; continua a partir do maior número existente (inclui backfill).
        """
        from sqlalchemy import text

        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(:k)"), {"k": self._SGC_LOCK_KEY}
        )
        current_max = (
            await self.db.execute(select(func.coalesce(func.max(ReceivableAdvanceBatch.sgc_number), 0)))
        ).scalar_one()
        return int(current_max or 0) + 1

    async def _allocate_batch_number(self, receive_date: date) -> str:
        year = receive_date.year
        rows = (
            await self.db.execute(
                select(ReceivableAdvanceBatch.batch_number).where(
                    ReceivableAdvanceBatch.batch_number.like(f"BT-{year}-%")
                )
            )
        ).scalars().all()
        return _next_batch_number(list(rows), year=year)

    async def _find_batch_payable_line(
        self,
        payables: PayableSnapshotService,
        *,
        month: date,
        operation_tag: str,
        name_suffix: str,
    ) -> PayableSnapshot | None:
        comp = normalize_competencia(month)
        for row in await payables.list_for_month(month=comp):
            if not _is_bordero_operation_payable(row, operation_tag=operation_tag):
                continue
            if name_suffix in str(getattr(row, "name", "") or ""):
                return row
        return None

    async def add_operation_payable_line(
        self,
        *,
        batch: ReceivableAdvanceBatch,
        month: date,
        name: str,
        amount: float,
        due_date: date,
        category: str = "Despesas financeiras",
        cost_center: str = "Financeiro",
        full_name: str | None = None,
    ) -> None:
        """Cria um lançamento em Contas a Pagar vinculado à operação (ref_id=batch.id).

        Helper genérico de infraestrutura: qualquer Operation Handler pode gerar
        efeitos de CAP sem conhecer os detalhes do snapshot. Garante o vínculo com
        o borderô para rastreabilidade/auditoria/reversão (regra 8).

        O tipo é `ANTECIPACAO_OPERACAO` (isolado da antecipação individual de NF; a UI
        exibe "Antecipação"). `full_name` guarda o nome completo em `observation` para o
        tooltip do CAP quando o `name` é apresentado de forma abreviada.
        """
        comp = normalize_competencia(month)
        payables = PayableSnapshotService(self.db)
        if not await payables.is_generated(month=comp):
            await payables.get_or_create_for_month(
                payment_month=comp,
                sees_all_projects=True,
                accessible_project_ids=None,
            )
        await payables.create_manual(
            month=comp,
            name=name,
            category=category,
            cost_center=cost_center,
            amount=amount,
            due_date=due_date,
            snapshot_type=PayableSnapshotType.ANTECIPACAO_OPERACAO,
            observation=(full_name or "").strip() or _batch_payable_observation(self._display_code(batch)),
            ref_id=batch.id,
        )

    async def _ensure_payables_for_batch(
        self,
        *,
        batch_number: str,
        institution: str,
        receive_date: date,
        repayment_date: date,
        discount_amount: float,
        fee_amount: float,
        batch_id: UUID | None = None,
    ) -> None:
        comp = normalize_competencia(receive_date)
        payables = PayableSnapshotService(self.db)
        if not await payables.is_generated(month=comp):
            await payables.get_or_create_for_month(
                payment_month=comp,
                sees_all_projects=True,
                accessible_project_ids=None,
            )

        inst = institution.strip()
        obs = _batch_payable_observation(batch_number)

        if discount_amount > 0.005:
            if await self._find_batch_payable_line(
                payables,
                month=comp,
                operation_tag=batch_number,
                name_suffix=_BATCH_DISCOUNT_SUFFIX,
            ) is None:
                await payables.create_manual(
                    month=comp,
                    name=f"{inst}{_BATCH_DISCOUNT_SUFFIX}",
                    category="Despesas financeiras",
                    cost_center="Financeiro",
                    amount=discount_amount,
                    due_date=receive_date,
                    observation=obs,
                    ref_id=batch_id,
                )
        if fee_amount > 0.005:
            if await self._find_batch_payable_line(
                payables,
                month=comp,
                operation_tag=batch_number,
                name_suffix=_BATCH_FEE_SUFFIX,
            ) is None:
                await payables.create_manual(
                    month=comp,
                    name=f"{inst}{_BATCH_FEE_SUFFIX}",
                    category="Despesas financeiras",
                    cost_center="Financeiro",
                    amount=fee_amount,
                    due_date=receive_date,
                    observation=obs,
                    ref_id=batch_id,
                )

    async def cancel_batch(
        self,
        *,
        batch_id: UUID,
        log_user: str | None = None,
    ) -> ReceivableAdvanceBatch:
        """
        Cancela um borderô (soft delete via status=CANCELLED), sem apagar histórico.

        - Desassocia NFs do lote
        - Remove despesas MANUAL do borderô somente se não houver pagamento nelas
        - Mantém compatibilidade com antecipação individual
        """
        batch = await self.get_batch(batch_id)
        if batch is None:
            raise ValueError("Borderô não encontrado.")
        if batch.status not in (ReceivableAdvanceBatchStatus.OPEN, ReceivableAdvanceBatchStatus.DRAFT):
            raise ValueError("Apenas operações em aberto ou rascunho podem ser canceladas.")

        # Reversão específica da instituição (ex.: Daycoval desfaz marcação de recebida).
        handler = AdvanceOperationService(self).resolve(await self._profile_for_batch(batch))
        handler_extra_months = await handler.on_cancel(batch, log_user=log_user)

        # Apaga despesas automáticas da operação (se não houver pagamentos registrados).
        payables = PayableSnapshotService(self.db)
        tag = _op_display_code(
            batch_number=batch.batch_number,
            operation_code=getattr(batch, "operation_code", None),
            batch_id=batch.id,
        )
        candidates = []
        for row in await payables.list_all():
            if not _row_belongs_to_batch(row, batch_id=batch.id, operation_tag=tag):
                continue
            if float(getattr(row, "amount_paid", 0) or 0) > 0.005:
                raise ValueError(
                    "Não é possível cancelar: despesas do borderô já possuem pagamento registrado."
                )
            candidates.append(row)

        for row in candidates:
            await payables.delete_row(row=row)

        recv_svc = ReceivableService(self.db)
        affected_months: set[date] = {
            normalize_competencia(batch.receive_date),
            normalize_competencia(batch.repayment_date),
        }
        affected_months |= handler_extra_months

        for item in batch.items or []:
            try:
                inv = item.invoice
            except MissingGreenlet:
                inv = None
            if inv is None:
                continue
            inv.advance_batch_id = None
            if (inv.invoice_status or "").upper() not in ("CANCELADA", "RECEBIDA"):
                inv.is_anticipated = False
            if log_user:
                recv_svc.append_log(inv, f"Borderô {batch.batch_number}: cancelado by={log_user}")
            affected_months |= get_affected_months(inv)

        batch.status = ReceivableAdvanceBatchStatus.CANCELLED
        await PayableSnapshotService(self.db).invalidate_months(months=affected_months)
        await self.db.flush()
        await self.db.refresh(batch)
        return batch

    async def delete_batch(
        self,
        *,
        batch_id: UUID,
        log_user: str | None = None,
    ) -> None:
        """
        Exclusão definitiva (para correção de erro operacional).

        Regras:
        - só permite se status=CANCELLED
        - não permite se houver pagamentos nas despesas automáticas do borderô
        """
        batch = await self.get_batch(batch_id)
        if batch is None:
            raise ValueError("Borderô não encontrado.")
        if batch.status != ReceivableAdvanceBatchStatus.CANCELLED:
            raise ValueError("Para excluir definitivamente, primeiro cancele o borderô.")

        # Segurança extra: garantir que não ficou despesa com pagamento.
        tag = _op_display_code(
            batch_number=batch.batch_number,
            operation_code=getattr(batch, "operation_code", None),
            batch_id=batch.id,
        )
        payables = PayableSnapshotService(self.db)
        for row in await payables.list_all():
            if not _row_belongs_to_batch(row, batch_id=batch.id, operation_tag=tag):
                continue
            if float(getattr(row, "amount_paid", 0) or 0) > 0.005:
                raise ValueError("Não é possível excluir: despesas do borderô já possuem pagamento registrado.")

        # NFs deveriam estar desassociadas no cancelamento; reforça idempotência.
        recv_svc = ReceivableService(self.db)
        for item in batch.items or []:
            try:
                inv = item.invoice
            except MissingGreenlet:
                inv = None
            if inv is None:
                continue
            inv.advance_batch_id = None
            if log_user:
                recv_svc.append_log(inv, f"Borderô {batch.batch_number}: excluído definitivamente by={log_user}")

        # Remove itens e o lote
        await self.db.delete(batch)
        await self.db.flush()

    async def _resolve_institution(
        self,
        *,
        institution_id: UUID | None,
        institution: str | None,
    ) -> tuple[str, UUID | None]:
        """Resolve (nome, id) da instituição. Prioriza o cadastro (institution_id);
        aceita texto livre como caminho legado/compatibilidade."""
        if institution_id is not None:
            row = await self.db.get(AdvanceInstitution, institution_id)
            if row is None:
                raise ValueError("Instituição não encontrada.")
            if not bool(row.is_active):
                raise ValueError("Instituição inativa não pode ser utilizada em novas operações.")
            return row.name, row.id
        text = (institution or "").strip()
        if not text:
            raise ValueError("Informe a instituição.")
        return text, None

    async def create_batch(
        self,
        *,
        operation_type: str = "BORDERO",
        operation_code: str | None = None,
        institution: str | None = None,
        institution_id: UUID | None = None,
        received_amount: float = 0,
        discount_amount: float = 0,
        fee_amount: float = 0,
        receive_date: date,
        repayment_date: date | None = None,
        observation: str | None,
        invoice_ids: list[UUID] | None = None,
        items_config: list[dict] | None = None,
        repasse_enabled: bool = False,
        created_by_id: UUID | None,
        log_user: str | None = None,
    ) -> ReceivableAdvanceBatch:
        inst_name, inst_id = await self._resolve_institution(
            institution_id=institution_id, institution=institution
        )

        # Normaliza a entrada: ou itens estruturados (com base por NF) ou apenas ids.
        if items_config:
            raw_pairs = [
                (cfg["invoice_id"], cfg.get("advance_basis"), cfg.get("advanced_amount"))
                for cfg in items_config
            ]
        else:
            raw_pairs = [(iid, None, None) for iid in (invoice_ids or [])]

        # Deduplica por invoice_id preservando ordem.
        seen: set[UUID] = set()
        pairs: list[tuple[UUID, str | None, float | None]] = []
        for iid, basis, manual in raw_pairs:
            if iid in seen:
                continue
            seen.add(iid)
            pairs.append((iid, basis, manual))
        if len(pairs) < 1:
            raise ValueError("Selecione ao menos 1 nota fiscal para o borderô.")

        items_input: list[tuple[ReceivableInvoice, str | None, float | None]] = []
        for iid, basis, manual in pairs:
            inv = await self.db.get(ReceivableInvoice, iid)
            if inv is None:
                raise ValueError("Uma ou mais notas fiscais não foram encontradas.")
            await self._validate_invoice_eligible(inv)
            items_input.append((inv, basis, manual))

        gross = round(sum(float(inv.gross_amount or 0) for inv, _b, _m in items_input), 2)
        if gross <= 0:
            raise ValueError("O valor bruto total das NFs deve ser positivo.")

        recv = round(float(received_amount or 0), 2)
        disc = round(float(discount_amount or 0), 2)
        fee = round(float(fee_amount or 0), 2)
        if recv < 0:
            raise ValueError("Valor líquido recebido inválido.")

        # Data de devolução é opcional: perfis sem devolução (ex.: Daycoval, onde a
        # ENEL paga o banco diretamente) não a informam. Persiste = recebimento para
        # não afetar a coluna NOT NULL nem a lógica de meses afetados (colapsa no mês
        # do recebimento — nenhum efeito financeiro adicional).
        effective_repayment_date = repayment_date or receive_date

        batch_number = await self._allocate_batch_number(receive_date)
        sgc_number = await self._allocate_sgc_number()
        batch = ReceivableAdvanceBatch(
            sgc_number=sgc_number,
            batch_number=batch_number,
            operation_type=str(operation_type or "BORDERO").strip() or "BORDERO",
            operation_code=(operation_code or "").strip() or None,
            institution=inst_name,
            institution_id=inst_id,
            gross_amount=gross,
            received_amount=recv,
            discount_amount=disc,
            fee_amount=fee,
            repasse_enabled=bool(repasse_enabled),
            receive_date=receive_date,
            repayment_date=effective_repayment_date,
            observation=(observation or "").strip() or None,
            status=ReceivableAdvanceBatchStatus.DRAFT,
            created_by_id=created_by_id,
        )
        self.db.add(batch)
        await self.db.flush()

        # Rascunho: monta os itens e os totais delegando ao Operation Handler da
        # instituição (base/valor antecipado por NF). Os efeitos financeiros
        # (marcar NFs, gerar CAP, invalidar snapshots) só ocorrem em confirm_batch.
        handler = AdvanceOperationService(self).resolve(await self._profile_for_batch(batch))
        await handler.prepare_draft(batch=batch, items_input=items_input)

        await self.db.flush()
        await self.db.refresh(batch)
        return batch

    @staticmethod
    def _safe_institution_ref(batch: ReceivableAdvanceBatch):
        """institution_ref carregada (selectinload) ou None — evita lazy-load (lazy='raise')."""
        try:
            return batch.institution_ref
        except Exception:
            return None

    def _display_code(self, batch: ReceivableAdvanceBatch) -> str:
        return _op_display_code(
            batch_number=batch.batch_number,
            operation_code=getattr(batch, "operation_code", None),
            batch_id=batch.id,
            sgc_number=getattr(batch, "sgc_number", None),
        )

    async def _profile_for_batch(self, batch: ReceivableAdvanceBatch) -> str | None:
        iid = getattr(batch, "institution_id", None)
        if iid is None:
            return None
        inst = await self.db.get(AdvanceInstitution, iid)
        return inst.operation_profile if inst else None

    async def _mark_invoices_anticipated(
        self, batch: ReceivableAdvanceBatch, *, log_user: str | None = None
    ) -> set[date]:
        """Marca as NFs do lote como ANTECIPADA (comportamento default). Retorna os meses afetados."""
        recv_svc = ReceivableService(self.db)
        affected: set[date] = {
            normalize_competencia(batch.receive_date),
            normalize_competencia(batch.repayment_date),
        }
        display_code = self._display_code(batch)
        for item in batch.items or []:
            try:
                inv = item.invoice
            except MissingGreenlet:
                inv = None
            if inv is None:
                inv = await self.db.get(ReceivableInvoice, item.invoice_id)
            if inv is None:
                continue
            inv.advance_batch_id = batch.id
            inv.is_anticipated = True
            inv.institution = batch.institution
            inv.invoice_status = derive_invoice_status(
                stored_status=inv.invoice_status,
                is_anticipated=True,
                received_amount=float(inv.received_amount or 0),
                net_amount=float(inv.net_amount or 0),
            )
            if log_user:
                recv_svc.append_log(
                    inv,
                    f"Antecipação {display_code}: via lote ({batch.institution}) by={log_user}",
                )
            affected |= get_affected_months(inv)
        return affected

    async def _liquidate_invoices(
        self, batch: ReceivableAdvanceBatch, *, log_user: str | None = None
    ) -> set[date]:
        """Liquida as NFs do lote: marca como RECEBIDAS e fora de vencimento/atraso.

        Building block genérico (infra reutilizável por qualquer perfil que liquide
        NFs na confirmação). As NFs continuam vinculadas ao borderô (rastreabilidade)
        e ficam com `include_in_dashboard=False` para não duplicar a receita — que já
        é contabilizada pela própria operação (fonte única).
        """
        recv_svc = ReceivableService(self.db)
        affected: set[date] = {
            normalize_competencia(batch.receive_date),
            normalize_competencia(batch.repayment_date),
        }
        display_code = self._display_code(batch)
        for item in batch.items or []:
            try:
                inv = item.invoice
            except MissingGreenlet:
                inv = None
            if inv is None:
                inv = await self.db.get(ReceivableInvoice, item.invoice_id)
            if inv is None:
                continue
            net = float(inv.net_amount or 0)
            inv.advance_batch_id = batch.id
            inv.is_anticipated = True
            inv.institution = batch.institution
            inv.received_amount = net
            inv.received_date = batch.receive_date
            inv.invoice_status = derive_invoice_status(
                stored_status=inv.invoice_status,
                is_anticipated=True,
                received_amount=net,
                net_amount=net,
            )
            inv.include_in_dashboard = False
            if log_user:
                recv_svc.append_log(
                    inv,
                    f"Antecipação {display_code}: NF liquidada (recebida via operação) by={log_user}",
                )
            affected |= get_affected_months(inv)
        return affected

    async def _revert_invoice_liquidation(
        self, batch: ReceivableAdvanceBatch, *, log_user: str | None = None
    ) -> set[date]:
        """Reverte a liquidação das NFs (cancelamento): volta a EMITIDA e reentra em vencimento/atraso."""
        recv_svc = ReceivableService(self.db)
        affected: set[date] = set()
        display_code = self._display_code(batch)
        for item in batch.items or []:
            try:
                inv = item.invoice
            except MissingGreenlet:
                inv = None
            if inv is None:
                inv = await self.db.get(ReceivableInvoice, item.invoice_id)
            if inv is None:
                continue
            if (inv.invoice_status or "").upper() != "RECEBIDA" or inv.advance_batch_id != batch.id:
                continue
            net = float(inv.net_amount or 0)
            inv.received_amount = 0
            inv.received_date = None
            inv.include_in_dashboard = True
            inv.is_anticipated = False
            inv.invoice_status = derive_invoice_status(
                stored_status="EMITIDA",
                is_anticipated=False,
                received_amount=0,
                net_amount=net,
            )
            if log_user:
                recv_svc.append_log(
                    inv,
                    f"Antecipação {display_code}: liquidação revertida (cancelamento) by={log_user}",
                )
            affected |= get_affected_months(inv)
        return affected

    async def set_actual_received(
        self, *, batch_id: UUID, actual: float, log_user: str | None = None
    ) -> ReceivableAdvanceBatch | None:
        """Informa o valor efetivamente recebido (realizado) da operação.

        Genérico para qualquer perfil com previsto×realizado. Preserva o previsto
        (`expected_amount`, nunca sobrescrito) e passa o Dashboard a refletir o
        realizado (`received_amount`). Não gera despesa para a diferença (regra 10).
        """
        batch = await self.get_batch(batch_id)
        if batch is None:
            return None
        if batch.status != ReceivableAdvanceBatchStatus.OPEN:
            raise ValueError("Só é possível informar o valor recebido em operações confirmadas.")
        val = round(float(actual), 2)
        if val < 0:
            raise ValueError("Valor recebido inválido.")
        if batch.expected_amount is None:
            batch.expected_amount = round(float(batch.received_amount or 0), 2)
        batch.actual_received_amount = val
        batch.received_amount = val
        if log_user:
            batch.observation = append_observation_line(
                batch.observation,
                f"Realizado informado: {val:.2f} (previsto {float(batch.expected_amount):.2f}) by={log_user}",
            )
        await self.db.flush()
        await self.db.refresh(batch)
        return batch

    async def confirm_batch(
        self, *, batch_id: UUID, log_user: str | None = None
    ) -> ReceivableAdvanceBatch:
        """Confirma uma operação em rascunho (DRAFT → OPEN), aplicando as regras da instituição."""
        batch = await self.get_batch(batch_id)
        if batch is None:
            raise ValueError("Operação não encontrada.")
        if batch.status != ReceivableAdvanceBatchStatus.DRAFT:
            raise ValueError("Apenas operações em rascunho podem ser confirmadas.")
        profile = await self._profile_for_batch(batch)
        handler = AdvanceOperationService(self).resolve(profile)
        await handler.on_confirm(batch, log_user=log_user)
        batch.status = ReceivableAdvanceBatchStatus.OPEN
        batch.confirmed_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(batch)
        return batch

    async def update_dashboard_inclusion(self, batch_id: UUID, *, include_in_dashboard: bool) -> ReceivableAdvanceBatch | None:
        batch = await self.get_batch(batch_id)
        if batch is None:
            return None
        apply_dashboard_inclusion_change(
            before=bool(batch.include_in_dashboard),
            after=include_in_dashboard,
            set_value=lambda v: setattr(batch, "include_in_dashboard", v),
            append_line=lambda line: setattr(batch, "observation", append_observation_line(batch.observation, line)),
        )
        await self.db.flush()
        await self.db.refresh(batch)
        return batch

    def batch_to_read(self, batch: ReceivableAdvanceBatch) -> dict:
        gross = float(batch.gross_amount or 0)
        disc = float(batch.discount_amount or 0)
        discount_percent = round((disc / gross) * 100.0, 2) if gross > 0.005 else None
        items_out: list[dict] = []
        invoices_net_total = 0.0
        for item in batch.items or []:
            try:
                inv = item.invoice
            except MissingGreenlet:
                inv = None
            if inv is not None:
                invoices_net_total += float(inv.net_amount or 0)
            items_out.append(
                {
                    "id": item.id,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                    "batch_id": item.batch_id,
                    "invoice_id": item.invoice_id,
                    "invoice_amount": float(item.invoice_amount),
                    "advance_basis": getattr(item, "advance_basis", None),
                    "advanced_amount": (
                        float(item.advanced_amount) if getattr(item, "advanced_amount", None) is not None else None
                    ),
                    "invoice_number": inv.nf_number if inv else None,
                    "client_name": inv.client_name if inv else None,
                    "project_name": (inv.project.name if inv and getattr(inv, "project", None) else None),
                    "competence_month": getattr(inv, "competence_month", None) if inv else None,
                    "gross_amount": float(inv.gross_amount or 0) if inv else None,
                    "net_amount": float(inv.net_amount or 0) if inv else None,
                    "issue_date": inv.issue_date if inv else None,
                    "due_date": inv.due_date if inv else None,
                    "invoice_status": (
                        derive_invoice_status(
                            stored_status=inv.invoice_status,
                            is_anticipated=bool(inv.is_anticipated),
                            received_amount=float(inv.received_amount or 0),
                            net_amount=float(inv.net_amount or 0),
                        )
                        if inv
                        else None
                    ),
                }
            )
        # Indicador operacional (apenas informativo): custo efetivo de antecipar as NFs.
        # Compara o total líquido original das NFs com o valor efetivamente recebido
        # (received_amount = realizado se informado, senão previsto). Não altera nenhuma
        # regra financeira — é só um percentual para leitura no detalhe da operação.
        invoices_net_total = round(invoices_net_total, 2)
        valor_recebido = float(batch.received_amount or 0)
        finance_cost_amount = round(invoices_net_total - valor_recebido, 2) if invoices_net_total > 0.005 else None
        finance_cost_percent = (
            round((invoices_net_total - valor_recebido) / invoices_net_total * 100.0, 2)
            if invoices_net_total > 0.005
            else None
        )
        return {
            "id": batch.id,
            "created_at": batch.created_at,
            "updated_at": batch.updated_at,
            "sgc_number": int(batch.sgc_number),
            "invoices_net_total": invoices_net_total,
            "finance_cost_amount": finance_cost_amount,
            "finance_cost_percent": finance_cost_percent,
            "batch_number": batch.batch_number,
            "operation_type": getattr(batch, "operation_type", "BORDERO") or "BORDERO",
            "operation_code": getattr(batch, "operation_code", None),
            "institution": batch.institution,
            "institution_id": getattr(batch, "institution_id", None),
            "institution_profile": (
                inst_ref.operation_profile if (inst_ref := self._safe_institution_ref(batch)) else None
            ),
            "gross_amount": gross,
            "received_amount": float(batch.received_amount),
            "expected_amount": (
                float(batch.expected_amount) if getattr(batch, "expected_amount", None) is not None else None
            ),
            "actual_received_amount": (
                float(batch.actual_received_amount)
                if getattr(batch, "actual_received_amount", None) is not None
                else None
            ),
            "discount_amount": disc,
            "fee_amount": float(batch.fee_amount or 0),
            "repasse_enabled": bool(getattr(batch, "repasse_enabled", False)),
            "repasse_amount": (
                float(batch.repasse_amount) if getattr(batch, "repasse_amount", None) is not None else None
            ),
            "receive_date": batch.receive_date,
            "repayment_date": batch.repayment_date,
            "confirmed_at": getattr(batch, "confirmed_at", None),
            "observation": batch.observation,
            "include_in_dashboard": bool(getattr(batch, "include_in_dashboard", True)),
            "status": batch.status.value,
            "created_by_id": batch.created_by_id,
            "items": items_out,
            "invoice_count": len(items_out),
            "discount_percent": discount_percent,
        }

    def batch_summary(self, batch: ReceivableAdvanceBatch | None) -> dict | None:
        if batch is None:
            return None
        return {
            "id": batch.id,
            "sgc_number": int(batch.sgc_number),
            "batch_number": batch.batch_number,
            "institution": batch.institution,
            "status": batch.status.value,
        }
