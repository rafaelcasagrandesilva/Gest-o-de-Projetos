from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.company_finance import CompanyFinancialItem, CompanyFinancialPayment, RenegotiationType
from app.models.company_finance import CompanyFinancialItemType
from app.models.employee import Employee
from app.schemas.company_finance import PagamentoMes
from app.services.employee_cost_service import calculate_clt_cost, calculate_pj_total_cost
from app.services.payable_snapshot_service import PayableSnapshotService
from app.services.settings_service import SettingsService


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def parse_month(s: str) -> date:
    parts = s.strip().split("-")
    if len(parts) != 2:
        raise ValueError("mes inválido")
    y, m = int(parts[0]), int(parts[1])
    return date(y, m, 1)


def _f(v: object) -> float:
    return float(v) if v is not None else 0.0


def _debt_base_amount(it: CompanyFinancialItem) -> float:
    """Saldo base para endividamento: renegociado (se aplicável) senão valor_referencia."""
    if getattr(it, "has_renegotiation", False) and getattr(it, "renegotiated_amount", None) is not None:
        return _f(it.renegotiated_amount)
    return _f(it.valor_referencia)


class CompanyFinanceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _payment_months_for_item(self, *, item_id: UUID) -> set[date]:
        rows = (
            await self.db.execute(
                select(CompanyFinancialPayment.competencia).where(CompanyFinancialPayment.item_id == item_id)
            )
        ).scalars().all()
        return set(rows)

    async def _sync_payables_for_company_finance_item(self, *, item_id: UUID, months: set[date]) -> None:
        if months:
            await PayableSnapshotService(self.db).sync_company_finance_item_months(item_id=item_id, months=months)

    async def list_items(self, tipo: str, competencia: str | None) -> list[dict]:
        q = (
            select(CompanyFinancialItem)
            .where(CompanyFinancialItem.tipo == tipo)
            .options(selectinload(CompanyFinancialItem.payments), selectinload(CompanyFinancialItem.employee))
            .order_by(CompanyFinancialItem.nome)
        )
        rows = (await self.db.execute(q)).scalars().unique().all()
        comp_date = parse_month(competencia) if competencia else None
        out: list[dict] = []
        for it in rows:
            out.append(await self._item_to_read(it, comp_date))
        return out

    async def _employee_base_value(self, emp: Employee, *, competencia: date) -> float:
        settings = await SettingsService(self.db).get_or_create()
        if (emp.employment_type or "").upper() == "CLT":
            return float(calculate_clt_cost(emp, settings, competencia.year, competencia.month))
        return float(calculate_pj_total_cost(emp))

    async def _item_to_read(self, it: CompanyFinancialItem, competencia: date | None) -> dict:
        pags = sorted(it.payments, key=lambda p: p.competencia)
        pagamentos = [PagamentoMes(mes=month_key(p.competencia), valor=_f(p.valor)).model_dump() for p in pags]
        total_pago = sum(_f(p.valor) for p in it.payments)
        ref = _f(it.valor_referencia)
        debt_base = _debt_base_amount(it) if it.tipo == "endividamento" else ref
        pago_mes = 0.0
        if competencia:
            for p in it.payments:
                if p.competencia == competencia:
                    pago_mes = _f(p.valor)
                    break

        item_type = getattr(it, "item_type", None)
        employee_id = getattr(it, "employee_id", None)
        percentual = float(getattr(it, "percentual", 0) or 0) if getattr(it, "percentual", None) is not None else None
        emp = getattr(it, "employee", None)
        employee_name = getattr(emp, "full_name", None) if emp is not None else None
        employee_employment_type = getattr(emp, "employment_type", None) if emp is not None else None

        # Para COLABORADOR_MATRIZ: valor_referencia é calculado a partir do custo do colaborador no mês.
        if it.tipo == "custo_fixo" and item_type == CompanyFinancialItemType.COLABORADOR_MATRIZ and emp and competencia and percentual is not None:
            base_val = await self._employee_base_value(emp, competencia=competencia)
            ref = round(float(base_val) * (float(percentual) / 100.0), 2)

        if it.tipo == "endividamento":
            restante = max(0.0, debt_base - total_pago)
            progresso = (total_pago / debt_base) if debt_base > 0 else 0.0
            status = "quitado" if progresso >= 1.0 else "ativo"
            return {
                "id": it.id,
                "tipo": it.tipo,
                "item_type": item_type.value if item_type is not None else None,
                "employee_id": employee_id,
                "employee_name": employee_name,
                "employee_employment_type": employee_employment_type,
                "percentual": percentual,
                "nome": it.nome,
                "valor_referencia": ref,
                "has_legal_process": bool(getattr(it, "has_legal_process", False)),
                "has_renegotiation": bool(getattr(it, "has_renegotiation", False)),
                "renegotiated_amount": _f(it.renegotiated_amount) if getattr(it, "renegotiated_amount", None) is not None else None,
                "renegotiation_type": getattr(it, "renegotiation_type", None).value
                if getattr(it, "renegotiation_type", None) is not None
                else None,
                "installment_count": getattr(it, "installment_count", None),
                "installment_value": _f(it.installment_value) if getattr(it, "installment_value", None) is not None else None,
                "pagamentos": pagamentos,
                "total_pago": total_pago,
                "restante": restante,
                "progresso": min(1.0, progresso),
                "status": status,
                "progresso_mes": None,
                "pago_mes": pago_mes,
            }

        progresso_mes = (pago_mes / ref) if ref > 0 else 0.0
        return {
            "id": it.id,
            "tipo": it.tipo,
            "item_type": item_type.value if item_type is not None else None,
            "employee_id": employee_id,
            "employee_name": employee_name,
            "employee_employment_type": employee_employment_type,
            "percentual": percentual,
            "nome": it.nome,
            "valor_referencia": ref,
            "has_legal_process": bool(getattr(it, "has_legal_process", False)),
            "has_renegotiation": bool(getattr(it, "has_renegotiation", False)),
            "renegotiated_amount": _f(it.renegotiated_amount) if getattr(it, "renegotiated_amount", None) is not None else None,
            "renegotiation_type": getattr(it, "renegotiation_type", None).value
            if getattr(it, "renegotiation_type", None) is not None
            else None,
            "installment_count": getattr(it, "installment_count", None),
            "installment_value": _f(it.installment_value) if getattr(it, "installment_value", None) is not None else None,
            "pagamentos": pagamentos,
            "total_pago": total_pago,
            "restante": None,
            "progresso": progresso_mes,
            "status": None,
            "progresso_mes": progresso_mes,
            "pago_mes": pago_mes,
        }

    async def create_item(self, *, actor_user_id: UUID, data: dict) -> CompanyFinancialItem:
        _ = actor_user_id
        rtype = data.get("renegotiation_type")
        renegotiation_type = RenegotiationType(rtype) if rtype is not None else None
        item_type_raw = data.get("item_type") or "MANUAL"
        item_type = CompanyFinancialItemType(item_type_raw)
        employee_id = data.get("employee_id")
        percentual = data.get("percentual")
        row = CompanyFinancialItem(
            tipo=data["tipo"],
            nome=data["nome"].strip(),
            valor_referencia=data["valor_referencia"],
            item_type=item_type,
            employee_id=employee_id,
            percentual=percentual,
            has_legal_process=bool(data.get("has_legal_process") or False),
            has_renegotiation=bool(data.get("has_renegotiation") or False),
            renegotiated_amount=data.get("renegotiated_amount"),
            renegotiation_type=renegotiation_type,
            installment_count=data.get("installment_count"),
            installment_value=data.get("installment_value"),
        )
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def update_item(self, *, item_id: UUID, data: dict) -> CompanyFinancialItem | None:
        row = await self.db.get(CompanyFinancialItem, item_id)
        if row is None:
            return None
        if "item_type" in data and data.get("item_type") is not None:
            row.item_type = CompanyFinancialItemType(data["item_type"])
        if "employee_id" in data:
            row.employee_id = data.get("employee_id")
        if "percentual" in data:
            row.percentual = data.get("percentual")
        if data.get("nome") is not None:
            row.nome = data["nome"].strip()
        if data.get("valor_referencia") is not None:
            row.valor_referencia = data["valor_referencia"]
        if data.get("has_legal_process") is not None:
            row.has_legal_process = bool(data["has_legal_process"])
        if data.get("has_renegotiation") is not None:
            row.has_renegotiation = bool(data["has_renegotiation"])
        if "renegotiated_amount" in data:
            row.renegotiated_amount = data.get("renegotiated_amount")
        if "renegotiation_type" in data:
            rtype = data.get("renegotiation_type")
            row.renegotiation_type = RenegotiationType(rtype) if rtype is not None else None
        if "installment_count" in data:
            row.installment_count = data.get("installment_count")
        if "installment_value" in data:
            row.installment_value = data.get("installment_value")

        if row.tipo != "endividamento":
            row.has_legal_process = False
            row.has_renegotiation = False
            row.renegotiated_amount = None
            row.renegotiation_type = None
            row.installment_count = None
            row.installment_value = None

        if row.tipo != "custo_fixo" or row.item_type != CompanyFinancialItemType.COLABORADOR_MATRIZ:
            row.employee_id = None
            row.percentual = None

        if row.tipo == "endividamento" and not row.has_renegotiation:
            row.renegotiated_amount = None
            row.renegotiation_type = None
            row.installment_count = None
            row.installment_value = None
        row.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(row)
        await self._sync_payables_for_company_finance_item(
            item_id=item_id,
            months=await self._payment_months_for_item(item_id=item_id),
        )
        return row

    async def delete_item(self, *, item_id: UUID) -> bool:
        row = await self.db.get(CompanyFinancialItem, item_id)
        if row is None:
            return False
        await PayableSnapshotService(self.db).preserve_or_remove_deleted_company_finance_item(item_id=item_id)
        await self.db.delete(row)
        await self.db.flush()
        return True

    async def replace_payments(self, *, item_id: UUID, pagamentos: list[dict]) -> CompanyFinancialItem | None:
        item = await self.db.get(CompanyFinancialItem, item_id)
        if item is None:
            return None

        incoming: dict[date, float] = {}
        for p in pagamentos:
            mes = p["mes"]
            comp = parse_month(mes)
            val = max(0.0, float(p.get("valor") or 0))
            incoming[comp] = val

        if not incoming:
            return item

        existing_rows = (
            await self.db.execute(
                select(CompanyFinancialPayment).where(
                    CompanyFinancialPayment.item_id == item_id,
                    CompanyFinancialPayment.competencia.in_(sorted(incoming)),
                )
            )
        ).scalars().all()
        existing = {p.competencia: _f(p.valor) for p in existing_rows}
        changed_months = {
            comp
            for comp, new_value in incoming.items()
            if round(existing.get(comp, 0.0), 2) != round(new_value, 2)
        }

        # Substitui somente as competências presentes no payload. Isso preserva histórico fora
        # da janela visível na tela e evita que uma edição em fevereiro apague pagamentos antigos.
        await self.db.execute(
            delete(CompanyFinancialPayment).where(
                CompanyFinancialPayment.item_id == item_id,
                CompanyFinancialPayment.competencia.in_(sorted(incoming)),
            )
        )
        for comp, val in incoming.items():
            if val <= 0:
                continue
            self.db.add(
                CompanyFinancialPayment(
                    item_id=item_id,
                    competencia=comp,
                    valor=val,
                )
            )
        item.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(item, attribute_names=["payments"])
        await self._sync_payables_for_company_finance_item(item_id=item_id, months=changed_months)
        return item

    async def kpis_endividamento(self, competencia: str) -> dict:
        items = (
            (
                await self.db.execute(
                    select(CompanyFinancialItem)
                    .where(CompanyFinancialItem.tipo == "endividamento")
                    .options(selectinload(CompanyFinancialItem.payments))
                )
            )
            .scalars()
            .unique()
            .all()
        )
        comp = parse_month(competencia)
        total_endividamento = sum(_debt_base_amount(i) for i in items)
        total_pago_mes = 0.0
        saldo_restante = 0.0
        for it in items:
            ref = _debt_base_amount(it)
            total_pago = sum(_f(p.valor) for p in it.payments)
            total_pago_mes += sum(_f(p.valor) for p in it.payments if p.competencia == comp)
            saldo_restante += max(0.0, ref - total_pago)
        return {
            "total_endividamento": total_endividamento,
            "total_pago_mes": total_pago_mes,
            "saldo_restante": saldo_restante,
            "quantidade_itens": len(items),
        }

    async def kpis_custos_fixos(self, competencia: str) -> dict:
        items = (
            (
                await self.db.execute(
                    select(CompanyFinancialItem)
                    .where(CompanyFinancialItem.tipo == "custo_fixo")
                    .options(selectinload(CompanyFinancialItem.payments), selectinload(CompanyFinancialItem.employee))
                )
            )
            .scalars()
            .unique()
            .all()
        )
        comp = parse_month(competencia)
        total_esperado_mes = 0.0
        for it in items:
            if getattr(it, "item_type", None) == CompanyFinancialItemType.COLABORADOR_MATRIZ and getattr(it, "employee", None) is not None and getattr(it, "percentual", None) is not None:
                base_val = await self._employee_base_value(it.employee, competencia=comp)  # type: ignore[arg-type]
                total_esperado_mes += round(float(base_val) * (float(it.percentual) / 100.0), 2)
            else:
                total_esperado_mes += _f(it.valor_referencia)
        total_pago_mes = 0.0
        for it in items:
            for p in it.payments:
                if p.competencia == comp:
                    total_pago_mes += _f(p.valor)
                    break
        return {
            "total_esperado_mes": total_esperado_mes,
            "total_pago_mes": total_pago_mes,
            "quantidade_itens": len(items),
        }

    async def chart_series(self, tipo: str, mes_inicio: str, mes_fim: str) -> list[dict]:
        items = (
            (
                await self.db.execute(
                    select(CompanyFinancialItem)
                    .where(CompanyFinancialItem.tipo == tipo)
                    .options(selectinload(CompanyFinancialItem.payments))
                )
            )
            .scalars()
            .unique()
            .all()
        )
        start = parse_month(mes_inicio)
        end = parse_month(mes_fim)
        if start > end:
            start, end = end, start

        months: list[date] = []
        cur = date(start.year, start.month, 1)
        end_m = date(end.year, end.month, 1)
        while cur <= end_m:
            months.append(cur)
            if cur.month == 12:
                cur = date(cur.year + 1, 1, 1)
            else:
                cur = date(cur.year, cur.month + 1, 1)

        points: list[dict] = []
        for m in months:
            mk = month_key(m)
            pagamentos_mes = 0.0
            for it in items:
                for p in it.payments:
                    if p.competencia == m:
                        pagamentos_mes += _f(p.valor)
                        break

            saldo_restante_total = None
            if tipo == "endividamento":
                saldo_restante_total = 0.0
                for it in items:
                    ref = _debt_base_amount(it)
                    cum = sum(_f(p.valor) for p in it.payments if p.competencia <= m)
                    saldo_restante_total += max(0.0, ref - cum)

            points.append(
                {
                    "mes": mk,
                    "pagamentos_mes": pagamentos_mes,
                    "saldo_restante_total": saldo_restante_total,
                }
            )
        return points
