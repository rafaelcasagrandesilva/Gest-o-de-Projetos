from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timezone
from math import pow
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.exc import MissingGreenlet
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.receivable import (
    DUE_DAYS_CHOICES,
    ReceivableInvoice,
    ReceivableInvoiceAnticipation,
    ReceivableInvoiceFile,
)
from app.services.payable_snapshot_service import PayableSnapshotService
from app.utils.dashboard_inclusion import apply_dashboard_inclusion_change
from app.utils.date_utils import normalize_competencia
from app.schemas.receivable import (
    CENT_TOL,
    ADV_TOL,
    compute_due_date,
    compute_implied_monthly_rate_percent,
    compute_interest_amount,
    derive_invoice_status,
)


def _f(v: object) -> float:
    return float(v) if v is not None else 0.0


def _round2(v: float) -> float:
    return round(float(v), 2)


def _compute_anticipation_interest(
    *,
    amount_received: float,
    amount_to_repay: float,
    due_date: date,
    base_date: date,
) -> tuple[float | None, float | None, float | None, int | None]:
    recv = float(amount_received or 0.0)
    repay = float(amount_to_repay or 0.0)
    if recv <= 0 or repay <= 0:
        return None, None, None, None
    juros_total = round(repay - recv, 2)
    if juros_total < 0:
        # dados inconsistentes; não exibir
        return None, None, None, None
    dias = (due_date - base_date).days
    taxa_percentual = round((juros_total / recv) * 100.0, 2) if recv > 0 else None
    taxa_mensal = None
    if dias and dias > 0 and recv > 0:
        taxa_mensal = round(((juros_total / recv) / (float(dias) / 30.0)) * 100.0, 2)
    return juros_total, taxa_percentual, taxa_mensal, int(dias)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    last = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def get_affected_months(invoice: ReceivableInvoice) -> set[date]:
    """
    Meses (competência) impactados por uma NF para invalidação de snapshots.

    Regra:
    - issue_date, due_date, received_date (se houver)
    - due_date de cada antecipação (se houver)
    """
    months: set[date] = set()

    def add_month(d: date | None) -> None:
        if d is None:
            return
        months.add(normalize_competencia(d))

    add_month(getattr(invoice, "issue_date", None))
    add_month(getattr(invoice, "due_date", None))
    add_month(getattr(invoice, "received_date", None))

    try:
        ants = list(getattr(invoice, "anticipations", []) or [])
    except MissingGreenlet:
        ants = []
    for ant in ants:
        add_month(getattr(ant, "received_date", None))
        add_month(getattr(ant, "due_date", None))

    return months


class ReceivableService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _has_anticipations(self, invoice_id: UUID) -> bool:
        q = select(func.count()).select_from(ReceivableInvoiceAnticipation).where(
            ReceivableInvoiceAnticipation.invoice_id == invoice_id
        )
        n = (await self.db.execute(q)).scalar_one()
        return int(n or 0) > 0

    def append_log(self, inv: ReceivableInvoice, line: str) -> None:
        prev = (inv.activity_log or "").strip()
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        new_line = f"[{ts}] {line}"
        inv.activity_log = (prev + "\n" + new_line).strip() if prev else new_line

    def _sync_due_date(self, inv: ReceivableInvoice) -> None:
        if inv.due_days in DUE_DAYS_CHOICES:
            inv.due_date = compute_due_date(inv.issue_date, inv.due_days)

    def _sync_effective_status(self, inv: ReceivableInvoice) -> None:
        """Persiste status derivado, exceto CANCELADA explícita."""
        if inv.invoice_status == "CANCELADA":
            return
        inv.invoice_status = derive_invoice_status(
            stored_status=inv.invoice_status,
            is_anticipated=inv.is_anticipated,
            received_amount=_f(inv.received_amount),
            net_amount=_f(inv.net_amount),
        )

    def _validate_full_receipt(self, inv: ReceivableInvoice) -> None:
        # Fluxo simplificado: recebimento é binário (0 ou total), controlado pela UI.
        ra = _f(inv.received_amount)
        if ra <= CENT_TOL:
            inv.received_date = None
            return
        if inv.received_date is None:
            raise ValueError("Informe a data do recebimento.")
        net = _f(inv.net_amount)
        if ra + CENT_TOL < net:
            raise ValueError("Recebimento deve quitar a NF (valor recebido não pode ser menor que o valor líquido).")

    def _validate_anticipation_details(self, inv: ReceivableInvoice) -> None:
        if not inv.is_anticipated:
            return
        # Modelo novo (1:N): se existem antecipações vinculadas, a validação de campos legados não deve bloquear updates de NF.
        # As validações de antecipação acontecem em `add_anticipation`/`delete_anticipation` e no schema de criação.
        try:
            ants = list(getattr(inv, "anticipations", []) or [])
        except MissingGreenlet:
            ants = []
        if ants:
            return
        ar = inv.advance_amount_received
        ad = inv.advance_amount_due
        dd = inv.advance_due_date
        if ar is None or ad is None or dd is None:
            raise ValueError(
                "Para NF antecipada, informe: valor recebido, valor a devolver e data de devolução."
            )
        ar_f = _f(ar)
        ad_f = _f(ad)
        if ar_f <= CENT_TOL or ad_f <= CENT_TOL:
            raise ValueError("Valores da antecipação devem ser positivos.")
        if ad_f + CENT_TOL < ar_f:
            raise ValueError("Valor a devolver deve ser maior ou igual ao valor recebido.")

    def invoice_to_read(self, inv: ReceivableInvoice, *, api_prefix: str = "/api/v1") -> dict:
        self._sync_effective_status(inv)
        gross = _f(inv.gross_amount)
        net = _f(inv.net_amount)
        recv = _f(inv.received_amount)
        interest = compute_interest_amount(
            is_anticipated=inv.is_anticipated, net_amount=net, received_amount=recv
        )
        # Em contexto async, acessar relationship não carregada pode disparar lazy-load e causar MissingGreenlet.
        try:
            anticipations = list(getattr(inv, "anticipations", []) or [])
        except MissingGreenlet:
            anticipations = []
        adv_recv = sum(_f(a.amount_received) for a in anticipations) if anticipations else _f(inv.advance_amount_received)
        adv_due = sum(_f(a.amount_to_repay) for a in anticipations) if anticipations else _f(inv.advance_amount_due)
        adv_cost: float | None = None
        adv_rate: float | None = None
        adv_monthly: float | None = None
        if inv.is_anticipated and adv_recv > CENT_TOL and adv_due > CENT_TOL:
            adv_cost = _round2(adv_due - adv_recv)
            adv_rate = round(((adv_due / adv_recv) - 1.0) * 100.0, 6)
            if inv.advance_due_date:
                days = max(1, (inv.advance_due_date - inv.issue_date).days)
                adv_monthly = round((pow((adv_due / adv_recv), (30.0 / float(days))) - 1.0) * 100.0, 6)
        eff = derive_invoice_status(
            stored_status=inv.invoice_status,
            is_anticipated=inv.is_anticipated,
            received_amount=recv,
            net_amount=net,
        )
        has_pdf = bool((inv.pdf_path or "").strip())
        pdf_url = f"{api_prefix}/invoices/{inv.id}/pdf/" if has_pdf else None
        try:
            files = list(getattr(inv, "files", []) or [])
        except MissingGreenlet:
            files = []
        pname = inv.project.name if inv.project else None
        try:
            batch = getattr(inv, "advance_batch", None)
        except MissingGreenlet:
            batch = None
        batch_summary = None
        if batch is not None:
            batch_summary = {
                "id": batch.id,
                "batch_number": batch.batch_number,
                "institution": batch.institution,
                "status": batch.status.value if hasattr(batch.status, "value") else str(batch.status),
            }
        ants_out: list[dict] = []
        for a in anticipations:
            base_date = getattr(a, "received_date", None) or (a.created_at.date() if getattr(a, "created_at", None) else date.today())
            jt, tp, tm, dias = _compute_anticipation_interest(
                amount_received=_f(a.amount_received),
                amount_to_repay=_f(a.amount_to_repay),
                due_date=a.due_date,
                base_date=base_date,
            )
            d: dict = {
                "id": a.id,
                "created_at": a.created_at,
                "updated_at": a.updated_at,
                "invoice_id": a.invoice_id,
                "include_in_dashboard": bool(getattr(a, "include_in_dashboard", True)),
                "institution": a.institution,
                "amount_received": _round2(_f(a.amount_received)),
                "amount_to_repay": _round2(_f(a.amount_to_repay)),
                "data_recebimento": getattr(a, "received_date", None),
                "due_date": a.due_date,
            }
            if jt is not None and tp is not None and dias is not None:
                d["juros_total"] = jt
                d["taxa_percentual"] = tp
                d["dias"] = dias
                if tm is not None and dias > 0:
                    d["taxa_mensal"] = tm
            ants_out.append(d)
        return {
            "id": inv.id,
            "created_at": inv.created_at,
            "updated_at": inv.updated_at,
            "project_id": inv.project_id,
            "project_name": pname,
            "number": inv.nf_number,
            "issue_date": inv.issue_date,
            "due_days": inv.due_days,
            "due_date": inv.due_date,
            "gross_amount": gross,
            "net_amount": net,
            "client_name": inv.client_name,
            "notes": inv.notes,
            "is_anticipated": bool(anticipations) or bool(inv.is_anticipated),
            "institution": inv.institution,
            "advance_amount_received": _round2(adv_recv) if (anticipations or inv.advance_amount_received is not None) else None,
            "advance_amount_due": _round2(adv_due) if (anticipations or inv.advance_amount_due is not None) else None,
            "advance_due_date": inv.advance_due_date,
            "anticipations": ants_out,
            "received_amount": recv,
            "received_date": inv.received_date,
            "interest_amount": interest,
            "advance_cost_value": adv_cost,
            "advance_interest_rate": adv_rate,
            "advance_monthly_rate": adv_monthly,
            "implied_monthly_rate_percent": compute_implied_monthly_rate_percent(
                gross_amount=gross, net_amount=net
            ),
            "status": eff,
            "has_pdf": has_pdf,
            "pdf_url": pdf_url,
            "pdf_files": [
                {
                    "id": f.id,
                    "created_at": f.created_at,
                    "updated_at": f.updated_at,
                    "invoice_id": f.invoice_id,
                    "file_name": f.file_name,
                    "content_type": f.content_type,
                    "size_bytes": int(f.size_bytes or 0),
                }
                for f in files
            ],
            "activity_log": inv.activity_log,
            "include_in_dashboard": bool(getattr(inv, "include_in_dashboard", True)),
            "advance_batch_id": inv.advance_batch_id,
            "advance_batch": batch_summary,
        }

    async def list_invoices(
        self,
        *,
        project_id: UUID | None,
        project_ids: list[UUID] | None = None,
        status: str | None = None,
        client_busca: str | None = None,
        year: int | None,
        month: int | None,
        period_field: str = "issue",
    ) -> list[ReceivableInvoice]:
        q = select(ReceivableInvoice).options(
            selectinload(ReceivableInvoice.project),
            selectinload(ReceivableInvoice.anticipations),
            selectinload(ReceivableInvoice.files),
        )
        if project_id is not None:
            q = q.where(ReceivableInvoice.project_id == project_id)
        elif project_ids is not None:
            if len(project_ids) == 0:
                return []
            q = q.where(ReceivableInvoice.project_id.in_(project_ids))
        if year is not None and month is not None:
            start, end = month_bounds(year, month)
            if period_field == "issue":
                q = q.where(and_(ReceivableInvoice.issue_date >= start, ReceivableInvoice.issue_date <= end))
            else:
                # Regra do contas a receber:
                # - Se NF foi recebida (received_date existe), ela "migra" para o mês do recebimento.
                # - Se não foi recebida, ela fica no mês do vencimento (due_date).
                q = q.where(
                    or_(
                        and_(ReceivableInvoice.received_date.is_not(None), ReceivableInvoice.received_date >= start, ReceivableInvoice.received_date <= end),
                        and_(ReceivableInvoice.received_date.is_(None), ReceivableInvoice.due_date >= start, ReceivableInvoice.due_date <= end),
                    )
                )
        if client_busca and client_busca.strip():
            pat = f"%{client_busca.strip()}%"
            q = q.where(ReceivableInvoice.client_name.ilike(pat))
        q = q.order_by(ReceivableInvoice.due_date.desc(), ReceivableInvoice.issue_date.desc())
        rows = (await self.db.execute(q)).scalars().unique().all()
        if status is None:
            return list(rows)
        out: list[ReceivableInvoice] = []
        for inv in rows:
            eff = derive_invoice_status(
                stored_status=inv.invoice_status,
                is_anticipated=inv.is_anticipated,
                received_amount=_f(inv.received_amount),
                net_amount=_f(inv.net_amount),
            )
            if eff == status:
                out.append(inv)
        return out

    async def kpis(
        self,
        *,
        project_id: UUID | None,
        project_ids: list[UUID] | None = None,
        year: int | None,
        month: int | None,
        period_field: str = "issue",
    ) -> dict:
        q = select(ReceivableInvoice).options(selectinload(ReceivableInvoice.project))
        if project_id is not None:
            q = q.where(ReceivableInvoice.project_id == project_id)
        elif project_ids is not None:
            if len(project_ids) == 0:
                return {
                    "total_a_receber": 0.0,
                    "total_bruto_a_receber": 0.0,
                    "recebido_no_mes": 0.0,
                    "em_atraso_valor": 0.0,
                    "total_nfs": 0,
                }
            q = q.where(ReceivableInvoice.project_id.in_(project_ids))
        if year is not None and month is not None:
            start, end = month_bounds(year, month)
            if period_field == "issue":
                q = q.where(and_(ReceivableInvoice.issue_date >= start, ReceivableInvoice.issue_date <= end))
            else:
                q = q.where(
                    or_(
                        and_(ReceivableInvoice.received_date.is_not(None), ReceivableInvoice.received_date >= start, ReceivableInvoice.received_date <= end),
                        and_(ReceivableInvoice.received_date.is_(None), ReceivableInvoice.due_date >= start, ReceivableInvoice.due_date <= end),
                    )
                )
        rows = (await self.db.execute(q)).scalars().unique().all()
        today = date.today()

        total_a_receber = 0.0
        total_bruto_a_receber = 0.0
        em_atraso_valor = 0.0
        for inv in rows:
            if inv.invoice_status == "CANCELADA":
                continue
            gross = _f(inv.gross_amount)
            net = _f(inv.net_amount)
            recv = _f(inv.received_amount)
            saldo = max(0.0, net - recv)
            if saldo > CENT_TOL:
                total_a_receber += saldo
                if net > CENT_TOL:
                    total_bruto_a_receber += gross * (saldo / net)
                else:
                    total_bruto_a_receber += gross
            if inv.due_date < today and recv < net - CENT_TOL and inv.invoice_status != "CANCELADA":
                em_atraso_valor += saldo

        # "Recebido no mês": segue o período selecionado.
        # Quando NÃO houver filtro por período (year/month vazios), este KPI vira consolidado:
        # soma total de recebidos no conjunto retornado.
        recebido_no_mes = 0.0
        if year is None or month is None:
            for inv in rows:
                if inv.invoice_status == "CANCELADA":
                    continue
                recebido_no_mes += _f(inv.received_amount)
        else:
            rs, re_ = month_bounds(year, month)
            for inv in rows:
                if inv.received_date and rs <= inv.received_date <= re_:
                    recebido_no_mes += _f(inv.received_amount)

        return {
            "total_a_receber": round(total_a_receber, 2),
            "total_bruto_a_receber": round(total_bruto_a_receber, 2),
            "recebido_no_mes": round(recebido_no_mes, 2),
            "em_atraso_valor": round(em_atraso_valor, 2),
            "total_nfs": len(rows),
        }

    async def get_invoice(self, invoice_id: UUID) -> ReceivableInvoice | None:
        q = (
            select(ReceivableInvoice)
            .where(ReceivableInvoice.id == invoice_id)
            .options(
                selectinload(ReceivableInvoice.project),
                selectinload(ReceivableInvoice.anticipations),
                selectinload(ReceivableInvoice.files),
                selectinload(ReceivableInvoice.advance_batch),
            )
        )
        return (await self.db.execute(q)).scalars().unique().one_or_none()

    async def add_anticipation(
        self,
        *,
        invoice_id: UUID,
        institution: str,
        amount_received: float,
        amount_to_repay: float,
        received_date: date,
        due_date: date,
        log_user: str | None = None,
        include_in_dashboard: bool = True,
    ) -> ReceivableInvoiceAnticipation:
        inv = await self.get_invoice(invoice_id)
        if inv is None:
            raise ValueError("NF não encontrada.")
        months_before = get_affected_months(inv)
        if inv.invoice_status == "CANCELADA":
            raise ValueError("Não é possível antecipar NF cancelada.")
        if inv.advance_batch_id is not None:
            raise ValueError("NF vinculada a um borderô. Remova do borderô antes de antecipar individualmente.")
        inst = (institution or "").strip()
        if not inst:
            raise ValueError("Informe a instituição.")
        ar = float(amount_received)
        ad = float(amount_to_repay)
        if ar <= 0 or ad <= 0:
            raise ValueError("Valores devem ser positivos.")
        if ad + ADV_TOL < ar:
            raise ValueError("amount_to_repay deve ser maior ou igual a amount_received.")

        # Regra de negócio: permitir soma das antecipações exceder o valor líquido da NF.

        row = ReceivableInvoiceAnticipation(
            invoice_id=invoice_id,
            institution=inst,
            amount_received=round(ar, 2),
            amount_to_repay=round(ad, 2),
            received_date=received_date,
            due_date=due_date,
            include_in_dashboard=bool(include_in_dashboard),
        )
        if log_user:
            self.append_log(inv, f"Antecipação adicionada: {inst} recv={round(ar,2)} repay={round(ad,2)} due={due_date.isoformat()} by={log_user}")
        inv.is_anticipated = True
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        # Invalida snapshots afetados (contas a pagar) para regeneração lazy no GET.
        months_after = set(months_before)
        months_after.add(normalize_competencia(due_date))
        await PayableSnapshotService(self.db).invalidate_months(months=months_after)
        return row

    async def delete_anticipation(
        self,
        *,
        invoice_id: UUID,
        anticipation_id: UUID,
        log_user: str | None = None,
    ) -> bool:
        inv = await self.get_invoice(invoice_id)
        if inv is None:
            raise ValueError("NF não encontrada.")
        months_before = get_affected_months(inv)
        row = await self.db.get(ReceivableInvoiceAnticipation, anticipation_id)
        if row is None or row.invoice_id != invoice_id:
            return False
        if log_user:
            self.append_log(inv, f"Antecipação removida: {row.institution} recv={_f(row.amount_received)} repay={_f(row.amount_to_repay)} due={row.due_date.isoformat()} by={log_user}")
        await self.db.delete(row)
        await self.db.flush()
        # se zerou antecipações, pode desmarcar flag legado
        remaining = list(getattr(inv, "anticipations", []) or [])
        if len(remaining) <= 1:
            # relationship pode ainda conter o row até expirar; força recomputo rápido no DB
            q = (
                select(ReceivableInvoiceAnticipation)
                .where(ReceivableInvoiceAnticipation.invoice_id == invoice_id)
                .limit(1)
            )
            any_left = (await self.db.execute(q)).scalars().first()
            if not any_left:
                if inv.advance_batch_id is None:
                    inv.is_anticipated = False
                    inv.institution = None
                    inv.advance_amount_received = None
                    inv.advance_amount_due = None
                    inv.advance_due_date = None
                    await self.db.flush()
        # Recarrega para computar meses após (sem a antecipação) e invalida união.
        inv_after = await self.get_invoice(invoice_id)
        months_after = get_affected_months(inv_after) if inv_after is not None else set()
        await PayableSnapshotService(self.db).invalidate_months(months=months_before | months_after)
        return True

    async def update_anticipation(
        self,
        *,
        invoice_id: UUID,
        anticipation_id: UUID,
        institution: str,
        amount_received: float,
        amount_to_repay: float,
        received_date: date,
        due_date: date,
        log_user: str | None = None,
        include_in_dashboard: bool | None = None,
    ) -> ReceivableInvoiceAnticipation | None:
        inv = await self.get_invoice(invoice_id)
        if inv is None:
            raise ValueError("NF não encontrada.")
        months_before = get_affected_months(inv)
        row = await self.db.get(ReceivableInvoiceAnticipation, anticipation_id)
        if row is None or row.invoice_id != invoice_id:
            return None

        apply_dashboard_inclusion_change(
            before=bool(row.include_in_dashboard),
            after=include_in_dashboard,
            set_value=lambda v: setattr(row, "include_in_dashboard", v),
            append_line=lambda line: self.append_log(inv, line),
        )

        inst = (institution or "").strip()
        if not inst:
            raise ValueError("Informe a instituição.")
        ar = float(amount_received)
        ad = float(amount_to_repay)
        if ar <= 0 or ad <= 0:
            raise ValueError("Valores devem ser positivos.")
        if ad + ADV_TOL < ar:
            raise ValueError("amount_to_repay deve ser maior ou igual a amount_received.")

        before_inst = row.institution
        before_ar = _round2(_f(row.amount_received))
        before_ad = _round2(_f(row.amount_to_repay))
        before_recv = getattr(row, "received_date", None)
        before_due = row.due_date

        row.institution = inst
        row.amount_received = round(ar, 2)
        row.amount_to_repay = round(ad, 2)
        row.received_date = received_date
        row.due_date = due_date
        row.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(row)

        if log_user:
            self.append_log(
                inv,
                "Antecipação editada: "
                f"{before_inst} recv={before_ar} → {round(ar,2)} repay={before_ad} → {round(ad,2)} "
                f"data_recebimento={before_recv.isoformat() if before_recv else '-'} → {received_date.isoformat()} "
                f"due={before_due.isoformat()} → {due_date.isoformat()} by={log_user}",
            )

        # Invalida snapshots afetados (contas a pagar) para regeneração lazy no GET.
        inv_after = await self.get_invoice(invoice_id)
        months_after = get_affected_months(inv_after) if inv_after is not None else set()
        months_after.add(normalize_competencia(due_date))
        await PayableSnapshotService(self.db).invalidate_months(months=months_before | months_after)
        return row

    async def create_invoice(self, data: dict, *, log_user: str | None = None) -> ReceivableInvoice:
        net = data.get("net_amount")
        if net is None:
            net = data["gross_amount"]
        due_days = int(data["due_days"])
        issue = data["issue_date"]
        due_date = compute_due_date(issue, due_days)
        row = ReceivableInvoice(
            project_id=data["project_id"],
            nf_number=data["number"].strip(),
            issue_date=issue,
            due_days=due_days,
            due_date=due_date,
            gross_amount=data["gross_amount"],
            net_amount=net,
            client_name=data.get("client_name"),
            notes=data.get("notes"),
            is_anticipated=False,
            received_amount=0,
            invoice_status="EMITIDA",
            include_in_dashboard=bool(data.get("include_in_dashboard", True)),
        )
        self._sync_effective_status(row)
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        await self.db.refresh(row, attribute_names=["project"])
        who = log_user or "sistema"
        self.append_log(row, f"NF criada por {who}.")
        await self.db.flush()
        # NF sem antecipação não altera contas a pagar (snapshot só inclui obrigações de antecipação).
        # Invalidar aqui apagava linhas geradas e perdia pagamentos registrados nos snapshots.
        return row

    async def update_invoice(self, invoice_id: UUID, data: dict, *, log_user: str | None = None) -> ReceivableInvoice | None:
        inv = await self.get_invoice(invoice_id)
        if inv is None:
            return None
        months_before = get_affected_months(inv)
        had_anticipations_before = await self._has_anticipations(invoice_id)
        if inv.invoice_status == "CANCELADA":
            if "notes" in data:
                inv.notes = data["notes"]
            apply_dashboard_inclusion_change(
                before=bool(inv.include_in_dashboard),
                after=data.get("include_in_dashboard"),
                set_value=lambda v: setattr(inv, "include_in_dashboard", v),
                append_line=lambda line: self.append_log(inv, line),
            )
            inv.updated_at = datetime.now(timezone.utc)
            await self.db.flush()
            await self.db.refresh(inv, attribute_names=["project"])
            if had_anticipations_before:
                await PayableSnapshotService(self.db).invalidate_months(months=months_before)
            return inv

        if "number" in data and data["number"] is not None:
            inv.nf_number = str(data["number"]).strip()
        if "issue_date" in data and data["issue_date"] is not None:
            inv.issue_date = data["issue_date"]
        if "due_days" in data and data["due_days"] is not None:
            inv.due_days = int(data["due_days"])
        if "gross_amount" in data and data["gross_amount"] is not None:
            inv.gross_amount = data["gross_amount"]
        if "net_amount" in data and data["net_amount"] is not None:
            inv.net_amount = data["net_amount"]
        if "client_name" in data:
            inv.client_name = data["client_name"]
        if "notes" in data:
            inv.notes = data["notes"]
        if "is_anticipated" in data and data["is_anticipated"] is not None:
            inv.is_anticipated = bool(data["is_anticipated"])
        if "institution" in data:
            inv.institution = data["institution"]
        if "advance_amount_received" in data:
            inv.advance_amount_received = data["advance_amount_received"]
        if "advance_amount_due" in data:
            inv.advance_amount_due = data["advance_amount_due"]
        if "advance_due_date" in data:
            inv.advance_due_date = data["advance_due_date"]
        if "received_amount" in data and data["received_amount"] is not None:
            inv.received_amount = data["received_amount"]
        if "received_date" in data:
            inv.received_date = data["received_date"]
        if "status" in data and data["status"] is not None:
            inv.invoice_status = data["status"]
        apply_dashboard_inclusion_change(
            before=bool(inv.include_in_dashboard),
            after=data.get("include_in_dashboard"),
            set_value=lambda v: setattr(inv, "include_in_dashboard", v),
            append_line=lambda line: self.append_log(inv, line),
        )

        self._sync_due_date(inv)
        # Validar campos de antecipação legados SOMENTE se o payload mexeu neles.
        # Não deve bloquear updates gerais (ex.: marcar como recebida) quando antecipações 1:N existem.
        if (
            ("is_anticipated" in data)
            or ("advance_amount_received" in data)
            or ("advance_amount_due" in data)
            or ("advance_due_date" in data)
            or ("institution" in data)
        ):
            self._validate_anticipation_details(inv)
        self._validate_full_receipt(inv)
        self._sync_effective_status(inv)
        inv.updated_at = datetime.now(timezone.utc)
        who = log_user or "sistema"
        self.append_log(inv, f"NF atualizada por {who}.")
        await self.db.flush()
        await self.db.refresh(inv, attribute_names=["project"])
        inv_after = await self.get_invoice(invoice_id)
        months_after = get_affected_months(inv_after) if inv_after is not None else set()
        has_anticipations_after = await self._has_anticipations(invoice_id)
        if had_anticipations_before or has_anticipations_after:
            await PayableSnapshotService(self.db).invalidate_months(months=months_before | months_after)
        return inv

    async def reactivate_invoice(
        self,
        invoice_id: UUID,
        *,
        actor_display: str,
        log_user: str | None = None,
    ) -> ReceivableInvoice | None:
        """
        Reativa NF cancelada por engano: CANCELADA → EMITIDA (ou status derivado dos recebimentos).

        Não altera valores, cliente, projeto, anexos nem demais campos.
        """
        inv = await self.get_invoice(invoice_id)
        if inv is None:
            return None
        prev_status = (inv.invoice_status or "").strip().upper()
        if prev_status != "CANCELADA":
            raise ValueError("Somente notas fiscais com status CANCELADA podem ser reativadas.")

        inv.invoice_status = "EMITIDA"
        self._sync_effective_status(inv)
        new_status = (inv.invoice_status or "").strip().upper()
        inv.updated_at = datetime.now(timezone.utc)

        now_br = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Sao_Paulo"))
        who = (actor_display or log_user or "sistema").strip()
        self.append_log(
            inv,
            f"NF {str(inv.nf_number).strip()} reativada por {who} em {now_br:%d/%m/%Y} às {now_br:%H:%M} "
            f"(status {prev_status} → {new_status}).",
        )
        await self.db.flush()
        await self.db.refresh(inv, attribute_names=["project"])
        return inv

    async def delete_invoice(self, invoice_id: UUID) -> bool:
        inv = await self.get_invoice(invoice_id)
        if inv is None:
            return False
        months_before = get_affected_months(inv)
        had_ants = await self._has_anticipations(invoice_id)
        await self.db.delete(inv)
        await self.db.flush()
        if had_ants:
            await PayableSnapshotService(self.db).invalidate_months(months=months_before)
        return True

    async def set_pdf_path(
        self, invoice_id: UUID, relative_path: str, *, log_user: str | None = None
    ) -> ReceivableInvoice | None:
        inv = await self.get_invoice(invoice_id)
        if inv is None:
            return None
        inv.pdf_path = relative_path
        inv.updated_at = datetime.now(timezone.utc)
        who = log_user or "sistema"
        self.append_log(inv, f"PDF da NF anexado ou atualizado por {who}.")
        await self.db.flush()
        return inv

    async def clear_pdf(self, invoice_id: UUID, *, log_user: str | None = None) -> ReceivableInvoice | None:
        inv = await self.get_invoice(invoice_id)
        if inv is None:
            return None
        inv.pdf_path = None
        inv.updated_at = datetime.now(timezone.utc)
        who = log_user or "sistema"
        self.append_log(inv, f"PDF da NF removido por {who}.")
        await self.db.flush()
        return inv
