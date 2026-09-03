from __future__ import annotations

import logging
import traceback
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.company_finance import CompanyFinancialItem, CompanyFinancialPayment, RenegotiationType
from app.models.company_finance import CompanyFinancialItemType
from app.models.employee import Employee
from app.models.legal import LegalPerson
from app.models.payable_payment import PayablePayment
from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
from app.schemas.company_finance import PagamentoMes
from app.services.company_finance_cost_center import (
    CompanyFinanceCostCenterService,
    default_label_for_tipo,
    default_system_for_tipo,
)
from app.services.employee_cost_service import calculate_clt_cost, calculate_pj_total_cost
from app.services.financial_schedule import (
    RangeSpec,
    ScheduleLine,
    build_schedule,
    compute_indicators,
    validate_closure,
)
from app.services.payable_snapshot_service import PayableSnapshotService, payable_snapshot_payment_status
from app.services.settings_service import SettingsService
from app.utils.lifecycle import DELETE_WITH_MOVEMENT_MSG, normalize_lifecycle

from app.utils.date_utils import next_competencia  # noqa: E402

logger = logging.getLogger(__name__)


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


def debt_base_amount(it: CompanyFinancialItem) -> float:
    """Base financeira ÚNICA da dívida (fonte da verdade — usar em TODOS os cálculos).

    Regra oficial: uma renegociação VÁLIDA substitui completamente o valor original.
        se has_renegotiation == True e renegotiated_amount > 0:
            base = renegotiated_amount
        senão:
            base = valor_referencia

    `renegotiated_amount <= 0` (inclui 0,00 de registros legados/UNIQUE incompletos) é tratado
    como "valor renegociado inexistente" → cai automaticamente no valor_referencia, sem alterar
    o dado persistido. Assim Valor da Dívida, Pago Total, Saldo Restante e % Quitado usam
    exatamente a mesma base.
    """
    reneg = getattr(it, "renegotiated_amount", None)
    if getattr(it, "has_renegotiation", False) and reneg is not None and _f(reneg) > 0:
        return _f(reneg)
    return _f(it.valor_referencia)


# Compat: nome anterior mantido como alias da fonte única (evita quebrar imports/chamadas).
_debt_base_amount = debt_base_amount


def debt_nome_for(
    *,
    employee_full_name: str | None,
    nome: str | None,
    item_description: str | None,
    legal_person_full_name: str | None = None,
) -> str:
    """Nome de um Endividamento (mesmo padrão do Custos Fixos).

    - Tipo Colaborador (colaborador vinculado) → nome = colaborador;
    - Tipo Desligado (pessoa do Jurídico) → nome = ex-colaborador;
    - Tipo Manual → nome informado pelo usuário;
    - Fallback de compatibilidade (registros/API sem nome) → a descrição.
    O nome NÃO embute mais a descrição (que passa a ser apenas complementar).

    Colaborador e Desligado são excludentes (o schema garante), então a ordem entre os dois
    aqui é indiferente — o que importa é que ambos vêm antes do nome digitado.
    """
    emp = (employee_full_name or "").strip()
    if emp:
        return emp
    desligado = (legal_person_full_name or "").strip()
    if desligado:
        return desligado
    name = (nome or "").strip()
    if name:
        return name
    return (item_description or "").strip()


def _default_category(tipo: str) -> str:
    return "Endividamento" if tipo == "endividamento" else "Custos diversos"


def _default_recurrence(tipo: str) -> str:
    return "INSTALLMENTS" if tipo == "endividamento" else "MONTHLY"


def is_lancamento_pendente(*, is_monthly_required: bool, has_value_in_competencia: bool) -> bool:
    """Regra pura: há pendência quando o item é obrigatório e não tem valor no mês.

    Não cria lançamento; apenas sinaliza ausência de valor na competência.
    """
    return bool(is_monthly_required) and not has_value_in_competencia


def last_known_payment(payments: list[tuple[date, float]], competencia: date) -> tuple[date, float] | None:
    """Último valor conhecido: competência anterior mais recente com valor > 0."""
    prior = [(comp, val) for comp, val in payments if comp < competencia and val > 0]
    if not prior:
        return None
    return max(prior, key=lambda cv: cv[0])


# Dia de vencimento assumido para renegociações sem dia configurado (dados legados).
DEFAULT_RENEGOTIATION_DUE_DAY = 20


def first_of_month(d: date) -> date:
    return date(d.year, d.month, 1)


def _default_entry_due(comp: date) -> date:
    """Vencimento padrão de um lançamento (dia 10 da competência, como no CAP)."""
    import calendar

    c = date(comp.year, comp.month, 1)
    last = calendar.monthrange(c.year, c.month)[1]
    return date(c.year, c.month, min(10, last))


def add_months(base: date, n: int) -> date:
    """Soma `n` meses a um primeiro-de-mês, retornando outro primeiro-de-mês."""
    total = (base.year * 12 + (base.month - 1)) + n
    y, m = divmod(total, 12)
    return date(y, m + 1, 1)


def months_between(a: date, b: date) -> int:
    """Diferença em meses (b - a), ignorando o dia."""
    return (b.year - a.year) * 12 + (b.month - a.month)


def renegotiation_installment_count(*, renegotiation_type: object, installment_count: object) -> int:
    """Quantidade de parcelas do cronograma: INSTALLMENTS usa a contagem; senão, parcela única."""
    rt = getattr(renegotiation_type, "value", renegotiation_type)
    if rt == "INSTALLMENTS" and installment_count:
        return int(installment_count)
    return 1


def parcela_prevista_na_competencia(*, anchor_month: date, installment_count: int, competencia: date) -> bool:
    """Regra pura: há parcela prevista na competência se ela cai dentro do cronograma.

    Cronograma mensal a partir de `anchor_month` (primeiro-de-mês da 1ª parcela),
    por `installment_count` meses. Não cria lançamento; apenas sinaliza expectativa.
    """
    diff = months_between(anchor_month, competencia)
    return 0 <= diff < max(1, int(installment_count))


class CompanyFinanceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        # Resumo da última sincronização grade→CAP (para o router avisar o usuário quando
        # algum mês não foi ajustado por já ter pagamento registrado).
        self.last_payable_sync: dict | None = None

    async def _payment_months_for_item(self, *, item_id: UUID) -> set[date]:
        rows = (
            await self.db.execute(
                select(CompanyFinancialPayment.competencia).where(CompanyFinancialPayment.item_id == item_id)
            )
        ).scalars().all()
        return set(rows)

    async def _entries_for_month(
        self, *, item_id: UUID, comp: date
    ) -> list[CompanyFinancialPayment]:
        """Lançamentos de um item na competência, ordenados por vencimento → criação.

        Ordenação estável (requisito de UX), independente da ordem de inserção.
        """
        rows = (
            await self.db.execute(
                select(CompanyFinancialPayment)
                .where(
                    CompanyFinancialPayment.item_id == item_id,
                    CompanyFinancialPayment.competencia == first_of_month(comp),
                )
                .order_by(
                    CompanyFinancialPayment.due_date.asc().nulls_last(),
                    CompanyFinancialPayment.created_at.asc(),
                )
            )
        ).scalars().all()
        return list(rows)

    async def _sync_payables_metadata_for_company_finance_item(self, *, item_id: UUID) -> None:
        await PayableSnapshotService(self.db).sync_company_finance_item_metadata(item_id=item_id)

    async def _sync_payables_for_company_finance_item(self, *, item_id: UUID, months: set[date]) -> dict:
        if not months:
            return {"synced": 0, "skipped_paid": []}
        return await PayableSnapshotService(self.db).sync_company_finance_item_months(
            item_id=item_id, months=months
        )

    async def list_items(self, tipo: str, competencia: str | None) -> list[dict]:
        q = (
            select(CompanyFinancialItem)
            .where(CompanyFinancialItem.tipo == tipo)
            .options(
                selectinload(CompanyFinancialItem.payments),
                selectinload(CompanyFinancialItem.employee),
                selectinload(CompanyFinancialItem.cost_center_project),
            )
            .order_by(CompanyFinancialItem.nome)
        )
        rows = (await self.db.execute(q)).scalars().unique().all()
        comp_date = parse_month(competencia) if competencia else None
        # Fonte única da verdade: consulta (somente leitura) o Contas a Pagar da competência
        # para espelhar pago/status no Extrato Analítico. NÃO gera snapshot nem altera nada.
        cap_map = await self._cap_rows_for_competence(list(rows), tipo, comp_date)
        # Modo 2: pago REAL do CAP carregado em lote (fonte única) e repassado ao cálculo oficial.
        sched_ids = [it.id for it in rows if self._uses_schedule(it)]
        pbe_all = await self._cap_paid_by_entry(sched_ids)
        pbm_all = await self._cap_paid_by_month(sched_ids)
        out: list[dict] = []
        for it in rows:
            kw = {}
            if self._uses_schedule(it):
                kw = {
                    "schedule_paid_by_entry": pbe_all,
                    "schedule_paid_by_month": pbm_all.get(it.id, {}),
                }
            out.append(await self._item_to_read(it, comp_date, cap_rows=cap_map.get(it.id), **kw))
        return out

    async def _cap_rows_for_competence(
        self, items: list[CompanyFinancialItem], tipo: str, comp_date: date | None
    ) -> dict[UUID, list[PayableSnapshot]]:
        """Títulos do Contas a Pagar (PayableSnapshot) da competência, agrupados por `ref_id`.

        Somente leitura: NÃO materializa nem gera — reflete o que já existe no CAP. Com
        múltiplos lançamentos há N títulos por item/mês (um por `entry_id`); a lista por item é
        agregada na leitura (soma pago/valor, status derivado). Vazio quando não há
        competência/itens.
        """
        if comp_date is None or not items:
            return {}
        types = (
            (PayableSnapshotType.FIXED_COST,)
            if tipo == "custo_fixo"
            else (PayableSnapshotType.ENDIVIDAMENTO, PayableSnapshotType.FINANCIAL)
        )
        ids = [it.id for it in items]
        rows = (
            await self.db.execute(
                select(PayableSnapshot).where(
                    PayableSnapshot.month == comp_date,
                    PayableSnapshot.ref_id.in_(ids),
                    PayableSnapshot.type.in_(types),
                )
            )
        ).scalars().all()
        out: dict[UUID, list[PayableSnapshot]] = {}
        for r in rows:
            if r.ref_id is None:
                continue
            out.setdefault(r.ref_id, []).append(r)
        return out

    async def _employee_full_name(self, employee_id: UUID | None) -> str | None:
        if employee_id is None:
            return None
        emp = await self.db.get(Employee, employee_id)
        return getattr(emp, "full_name", None) if emp is not None else None

    async def _legal_person_full_name(self, legal_person_id: UUID | None) -> str | None:
        if legal_person_id is None:
            return None
        person = await self.db.get(LegalPerson, legal_person_id)
        return getattr(person, "full_name", None) if person is not None else None

    async def _employee_base_value(self, emp: Employee, *, competencia: date) -> float:
        settings = await SettingsService(self.db).get_or_create()
        if (emp.employment_type or "").upper() == "CLT":
            return float(calculate_clt_cost(emp, settings, competencia.year, competencia.month))
        return float(calculate_pj_total_cost(emp))

    async def _cost_center_fields(self, it: CompanyFinancialItem) -> dict[str, object]:
        cc_svc = CompanyFinanceCostCenterService(self.db)
        label = await cc_svc.resolve_label(it)
        ref = await cc_svc.resolve_ref(it)
        it.cost_center = label
        return {
            "cost_center_ref": ref,
            "cost_center": label,
            "cost_center_project_id": getattr(it, "cost_center_project_id", None),
            "cost_center_system": getattr(it, "cost_center_system", None),
        }

    async def _item_to_read(
        self,
        it: CompanyFinancialItem,
        competencia: date | None,
        cap_rows: list[PayableSnapshot] | None = None,
        *,
        schedule_paid_by_entry: dict[UUID, float] | None = None,
        schedule_paid_by_month: dict[date, float] | None = None,
    ) -> dict:
        # Múltiplos lançamentos por competência: a grade exibe SEMPRE a SOMA do mês (a tela
        # principal permanece limpa). Agrega valor e CONTAGEM por competência; `count` alimenta
        # o indicador discreto "(N)" no frontend (só relevante quando > 1).
        by_month: dict[date, float] = {}
        by_month_count: dict[date, int] = {}
        for p in it.payments:
            by_month[p.competencia] = by_month.get(p.competencia, 0.0) + _f(p.valor)
            by_month_count[p.competencia] = by_month_count.get(p.competencia, 0) + 1
        pagamentos = [
            PagamentoMes(mes=month_key(m), valor=v, count=by_month_count.get(m, 0)).model_dump()
            for m, v in sorted(by_month.items())
        ]
        total_pago = sum(_f(p.valor) for p in it.payments)
        ref = _f(it.valor_referencia)
        debt_base = _debt_base_amount(it) if it.tipo == "endividamento" else ref
        pago_mes = round(by_month.get(competencia, 0.0), 2) if competencia else 0.0

        item_type = getattr(it, "item_type", None)
        employee_id = getattr(it, "employee_id", None)
        percentual = float(getattr(it, "percentual", 0) or 0) if getattr(it, "percentual", None) is not None else None
        emp = getattr(it, "employee", None)
        employee_name = getattr(emp, "full_name", None) if emp is not None else None
        # Ex-colaborador do Jurídico: só endividamento usa, e é apenas identificação.
        legal_person_id = getattr(it, "legal_person_id", None)
        legal_person_name = await self._legal_person_full_name(legal_person_id)
        employee_employment_type = getattr(emp, "employment_type", None) if emp is not None else None

        # Para COLABORADOR_MATRIZ: valor_referencia é calculado a partir do custo do colaborador no mês.
        if it.tipo == "custo_fixo" and item_type == CompanyFinancialItemType.COLABORADOR_MATRIZ and emp and competencia and percentual is not None:
            base_val = await self._employee_base_value(emp, competencia=competencia)
            ref = round(float(base_val) * (float(percentual) / 100.0), 2)

        cc_fields = await self._cost_center_fields(it)

        # Espelho do Contas a Pagar da competência (fonte oficial de pagamento/status para o
        # Extrato Analítico). Com N lançamentos há N títulos por item/mês: agrega pago e valor
        # e deriva o status do conjunto (PAGO só quando TODOS quitados; PARCIAL se há pagamento).
        rows = cap_rows or []
        cap_paid = sum(_f(r.amount_paid) for r in rows)
        cap_final = sum(_f(r.amount_final) for r in rows)
        cap_fields = {
            "cap_has_line": len(rows) > 0,
            "cap_amount_paid": round(cap_paid, 2),
            "cap_status": (
                payable_snapshot_payment_status(amount_paid=cap_paid, amount_final=cap_final)
                if rows
                else None
            ),
            "cap_is_obsolete": bool(rows) and all(getattr(r, "is_obsolete", False) for r in rows),
        }

        if it.tipo == "endividamento":
            schedule_dict = None
            if self._uses_schedule(it):
                # Modo 2: fonte ÚNICA — pago/saldo/progresso/status vêm do CAP (pagamentos reais),
                # nunca da soma das parcelas planejadas. Um só cálculo oficial (_schedule_execution).
                pbe = schedule_paid_by_entry
                if pbe is None:
                    pbe = await self._cap_paid_by_entry([it.id])
                ind = self._schedule_execution(it, pbe)
                total_pago = float(ind.total_pago)
                restante = float(ind.saldo_restante)
                progresso = ind.progresso
                status = "quitado" if progresso >= 1.0 else "ativo"
                schedule_dict = self._schedule_execution_dict(ind)
                if competencia is not None:
                    pbm = schedule_paid_by_month
                    if pbm is None:
                        pbm = (await self._cap_paid_by_month([it.id])).get(it.id, {})
                    pago_mes = round(pbm.get(competencia, 0.0), 2)
                else:
                    pago_mes = 0.0
            else:
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
                "legal_person_id": legal_person_id,
                "legal_person_name": legal_person_name,
                "percentual": percentual,
                "nome": it.nome,
                "item_description": getattr(it, "item_description", None),
                "valor_referencia": ref,
                "debt_base": debt_base,
                "category": getattr(it, "category", None) or _default_category(it.tipo),
                **cc_fields,
                **cap_fields,
                "description": getattr(it, "description", None),
                "recurrence": getattr(it, "recurrence", None) or _default_recurrence(it.tipo),
                "is_monthly_required": bool(getattr(it, "is_monthly_required", False)),
                "is_active": bool(getattr(it, "is_active", True)),
                "start_date": getattr(it, "start_date", None),
                "end_date": getattr(it, "end_date", None),
                "has_legal_process": bool(getattr(it, "has_legal_process", False)),
                "has_renegotiation": bool(getattr(it, "has_renegotiation", False)),
                "renegotiated_amount": _f(it.renegotiated_amount) if getattr(it, "renegotiated_amount", None) is not None else None,
                "renegotiation_type": getattr(it, "renegotiation_type", None).value
                if getattr(it, "renegotiation_type", None) is not None
                else None,
                "installment_count": getattr(it, "installment_count", None),
                "installment_value": _f(it.installment_value) if getattr(it, "installment_value", None) is not None else None,
                "renegotiation_agreement_date": getattr(it, "renegotiation_agreement_date", None),
                "renegotiation_first_payment_date": getattr(it, "renegotiation_first_payment_date", None),
                "renegotiation_due_day": getattr(it, "renegotiation_due_day", None),
                "uses_custom_schedule": bool(getattr(it, "uses_custom_schedule", False)),
                "pagamentos": pagamentos,
                "total_pago": total_pago,
                "restante": restante,
                "progresso": min(1.0, progresso),
                "status": status,
                "progresso_mes": None,
                "pago_mes": pago_mes,
                # Contrato de leitura do Modo 2 (fonte única). None no Modo 1 (inalterado).
                "schedule": schedule_dict,
            }

        progresso_mes = (pago_mes / ref) if ref > 0 else 0.0
        return {
            "id": it.id,
            "tipo": it.tipo,
            "item_type": item_type.value if item_type is not None else None,
            "employee_id": employee_id,
            "employee_name": employee_name,
            "employee_employment_type": employee_employment_type,
            "legal_person_id": legal_person_id,
            "legal_person_name": legal_person_name,
            "percentual": percentual,
            "nome": it.nome,
            "item_description": getattr(it, "item_description", None),
            "valor_referencia": ref,
            "debt_base": debt_base,
            "category": getattr(it, "category", None) or _default_category(it.tipo),
            **cc_fields,
            **cap_fields,
            "description": getattr(it, "description", None),
            "recurrence": getattr(it, "recurrence", None) or _default_recurrence(it.tipo),
            "is_monthly_required": bool(getattr(it, "is_monthly_required", False)),
            "is_active": bool(getattr(it, "is_active", True)),
            "start_date": getattr(it, "start_date", None),
            "end_date": getattr(it, "end_date", None),
            "has_legal_process": bool(getattr(it, "has_legal_process", False)),
            "has_renegotiation": bool(getattr(it, "has_renegotiation", False)),
            "renegotiated_amount": _f(it.renegotiated_amount) if getattr(it, "renegotiated_amount", None) is not None else None,
            "renegotiation_type": getattr(it, "renegotiation_type", None).value
            if getattr(it, "renegotiation_type", None) is not None
            else None,
            "installment_count": getattr(it, "installment_count", None),
            "installment_value": _f(it.installment_value) if getattr(it, "installment_value", None) is not None else None,
            "renegotiation_agreement_date": getattr(it, "renegotiation_agreement_date", None),
            "renegotiation_first_payment_date": getattr(it, "renegotiation_first_payment_date", None),
            "renegotiation_due_day": getattr(it, "renegotiation_due_day", None),
            "uses_custom_schedule": bool(getattr(it, "uses_custom_schedule", False)),
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
        is_active = bool(data.get("is_active", True))
        end_date = normalize_lifecycle(is_active=is_active, end_date=data.get("end_date"))

        # Endividamento: colaborador é só identificação (nunca matriz/percentual); a
        # descrição própria é o identificador e o `nome` é composto automaticamente.
        item_description = (data.get("item_description") or "").strip() or None
        if data["tipo"] == "endividamento":
            # Padrão Custos Fixos: Tipo Manual (Nome) ou Colaborador (colaborador). O
            # colaborador é só identificação — nunca matriz/percentual. Descrição é
            # complementar (opcional). item_type permanece MANUAL (compatibilidade).
            item_type = CompanyFinancialItemType.MANUAL
            percentual = None
            emp_name = await self._employee_full_name(employee_id)
            legal_name = await self._legal_person_full_name(data.get("legal_person_id"))
            nome = debt_nome_for(
                employee_full_name=emp_name,
                legal_person_full_name=legal_name,
                nome=data.get("nome"),
                item_description=item_description,
            )
        else:
            item_description = None
            nome = (data.get("nome") or "").strip()

        row = CompanyFinancialItem(
            tipo=data["tipo"],
            nome=nome,
            item_description=item_description,
            valor_referencia=data["valor_referencia"],
            is_active=is_active,
            start_date=data.get("start_date"),
            end_date=end_date,
            category=(data.get("category") or _default_category(data["tipo"])).strip(),
            description=(data.get("description") or None),
            recurrence=(data.get("recurrence") or _default_recurrence(data["tipo"])).strip(),
            item_type=item_type,
            employee_id=employee_id,
            # Só endividamento carrega este vínculo; o schema já zera nos demais tipos.
            legal_person_id=data.get("legal_person_id"),
            percentual=percentual,
            is_monthly_required=bool(data.get("is_monthly_required") or False),
            has_legal_process=bool(data.get("has_legal_process") or False),
            has_renegotiation=bool(data.get("has_renegotiation") or False),
            renegotiated_amount=data.get("renegotiated_amount"),
            renegotiation_type=renegotiation_type,
            installment_count=data.get("installment_count"),
            installment_value=data.get("installment_value"),
            renegotiation_agreement_date=data.get("renegotiation_agreement_date"),
            renegotiation_first_payment_date=data.get("renegotiation_first_payment_date"),
            renegotiation_due_day=data.get("renegotiation_due_day"),
            uses_custom_schedule=bool(data.get("uses_custom_schedule") or False),
            cost_center=default_label_for_tipo(data["tipo"]),
            cost_center_system=default_system_for_tipo(data["tipo"]),
        )
        self.db.add(row)
        await self.db.flush()
        ref_raw = data.get("cost_center_ref")
        if not ref_raw:
            raise ValueError("Centro de custo é obrigatório.")
        await CompanyFinanceCostCenterService(self.db).apply_ref(row, str(ref_raw))
        await self.db.refresh(row)
        return row

    async def update_item(self, *, item_id: UUID, data: dict) -> CompanyFinancialItem | None:
        row = await self.db.get(CompanyFinancialItem, item_id)
        if row is None:
            return None
        await CompanyFinanceCostCenterService(self.db).migrate_legacy_row(row)
        if "item_type" in data and data.get("item_type") is not None:
            row.item_type = CompanyFinancialItemType(data["item_type"])
        if "employee_id" in data:
            row.employee_id = data.get("employee_id")
        if "legal_person_id" in data:
            row.legal_person_id = data.get("legal_person_id")
        if "percentual" in data:
            row.percentual = data.get("percentual")
        if data.get("nome") is not None:
            row.nome = data["nome"].strip()
        if "item_description" in data:
            raw = data.get("item_description")
            row.item_description = str(raw).strip() if raw is not None and str(raw).strip() else None
        if data.get("valor_referencia") is not None:
            row.valor_referencia = data["valor_referencia"]
        if "category" in data:
            row.category = (data.get("category") or _default_category(row.tipo)).strip()
        if "cost_center_ref" in data and data.get("cost_center_ref") is not None:
            cc_svc = CompanyFinanceCostCenterService(self.db)
            await cc_svc.apply_ref(
                row,
                str(data["cost_center_ref"]),
                allow_inactive_project_id=getattr(row, "cost_center_project_id", None),
            )
        if "description" in data:
            raw = data.get("description")
            row.description = str(raw).strip() if raw is not None and str(raw).strip() else None
        if "recurrence" in data:
            row.recurrence = (data.get("recurrence") or _default_recurrence(row.tipo)).strip()
        if data.get("is_monthly_required") is not None:
            row.is_monthly_required = bool(data["is_monthly_required"])
        # Ciclo de vida do cadastro.
        if "start_date" in data:
            row.start_date = data.get("start_date")
        if data.get("is_active") is not None:
            row.is_active = bool(data["is_active"])
        if "end_date" in data:
            row.end_date = data.get("end_date")
        # Invariante (só quando status/encerramento é tocado): inativo exige end_date;
        # ativo limpa o encerramento (reativar reabre o ciclo de vida).
        lifecycle_touched = ("is_active" in data and data.get("is_active") is not None) or (
            "end_date" in data
        )
        if lifecycle_touched:
            row.end_date = normalize_lifecycle(is_active=bool(row.is_active), end_date=row.end_date)
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
        if "renegotiation_agreement_date" in data:
            row.renegotiation_agreement_date = data.get("renegotiation_agreement_date")
        if "renegotiation_first_payment_date" in data:
            row.renegotiation_first_payment_date = data.get("renegotiation_first_payment_date")
        if "renegotiation_due_day" in data:
            row.renegotiation_due_day = data.get("renegotiation_due_day")
        if data.get("uses_custom_schedule") is not None:
            row.uses_custom_schedule = bool(data["uses_custom_schedule"])

        if row.tipo != "endividamento":
            row.has_legal_process = False
            row.has_renegotiation = False
            row.renegotiated_amount = None
            row.renegotiation_type = None
            row.installment_count = None
            row.installment_value = None
            row.renegotiation_agreement_date = None
            row.renegotiation_first_payment_date = None
            row.renegotiation_due_day = None
            row.uses_custom_schedule = False

        # Custo Fixo: colaborador/percentual só existem em COLABORADOR_MATRIZ. Endividamento
        # mantém o colaborador (só identificação), mas nunca usa matriz/percentual.
        if row.tipo == "endividamento":
            row.item_type = CompanyFinancialItemType.MANUAL
            row.percentual = None
            # Colaborador → nome = colaborador; Manual → nome informado (já aplicado acima
            # a partir de data["nome"], se enviado). Descrição é apenas complementar.
            emp_name = await self._employee_full_name(row.employee_id)
            legal_name = await self._legal_person_full_name(row.legal_person_id)
            row.nome = debt_nome_for(
                employee_full_name=emp_name,
                legal_person_full_name=legal_name,
                nome=row.nome,
                item_description=row.item_description,
            ) or row.nome
        else:
            row.legal_person_id = None
            if row.item_type != CompanyFinancialItemType.COLABORADOR_MATRIZ:
                row.employee_id = None
                row.percentual = None

        if row.tipo == "endividamento" and not row.has_renegotiation:
            row.renegotiated_amount = None
            row.renegotiation_type = None
            row.installment_count = None
            row.installment_value = None
            row.renegotiation_agreement_date = None
            row.renegotiation_first_payment_date = None
            row.renegotiation_due_day = None
            # Sem renegociação não há cronograma: volta ao Modo 1 (parcelas iguais).
            row.uses_custom_schedule = False
        row.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(row)
        await self._sync_payables_metadata_for_company_finance_item(item_id=item_id)
        # ENCERRAR precisa matar as obrigações automáticas ABERTAS do mês do encerramento
        # em diante. Sem isto o cadastro ficava inativo mas as parcelas seguiam vivas no
        # Contas a Pagar, inclusive em competências futuras — e como excluir o item é
        # bloqueado quando há movimentação, não havia saída pela tela.
        #
        # SÓ roda quando o ciclo de vida foi tocado NESTA edição. Rodar em toda edição faria
        # uma troca de nome ou de centro de custo num item encerrado meses atrás apagar
        # títulos abertos sem ninguém ter pedido.
        if lifecycle_touched:
            await PayableSnapshotService(self.db).close_company_finance_item_payables(
                item_id=item_id
            )
        return row

    async def delete_item(self, *, item_id: UUID) -> bool:
        row = await self.db.get(CompanyFinancialItem, item_id)
        if row is None:
            return False
        # Exclusão física bloqueada quando há movimentação (pagamentos lançados): o
        # cadastro deve ser inativado para preservar o histórico financeiro.
        movement = int(
            (
                await self.db.execute(
                    select(func.count())
                    .select_from(CompanyFinancialPayment)
                    .where(CompanyFinancialPayment.item_id == item_id)
                )
            ).scalar_one()
            or 0
        )
        if movement > 0:
            raise ValueError(DELETE_WITH_MOVEMENT_MSG)
        await PayableSnapshotService(self.db).preserve_or_remove_deleted_company_finance_item(item_id=item_id)
        await self.db.delete(row)
        await self.db.flush()
        return True

    async def replace_payments(
        self, *, item_id: UUID, pagamentos: list[dict], zero_explicito: bool = False
    ) -> CompanyFinancialItem | None:
        logger.info(
            "company_finance.replace_payments service START item_id=%s pagamentos=%s",
            item_id,
            pagamentos,
        )
        try:
            item = await self.db.get(CompanyFinancialItem, item_id)
            if item is None:
                logger.warning("company_finance.replace_payments service item_id=%s not found", item_id)
                return None
            if self._uses_schedule(item):
                # Modo 2: a execução da dívida é o Cronograma (fonte única). A grade mensal é
                # somente leitura — toda alteração passa por replace_schedule.
                raise ValueError("Item em modo Cronograma: edite as parcelas pelo Cronograma, não pela grade mensal.")

            logger.info("company_finance.replace_payments service BEFORE migrate_legacy_row item_id=%s", item_id)
            await CompanyFinanceCostCenterService(self.db).migrate_legacy_row(item)
            logger.info("company_finance.replace_payments service AFTER migrate_legacy_row item_id=%s", item_id)

            # `None` = caixa ESVAZIADA (o mês volta ao valor de REFERÊNCIA);
            # `0` = zero DECLARADO ("neste mês não se paga nada", sem título no CAP).
            # Achatar os dois em 0, como antes, tornava impossível declarar zero: digitar
            # 0,00 apagava o lançamento e o título renascia com o valor de referência.
            incoming: dict[date, float | None] = {}
            for p in pagamentos:
                mes = p["mes"]
                comp = parse_month(mes)
                raw = p.get("valor")
                val = None if raw is None else max(0.0, float(raw))
                # Cliente sem o opt-in (JS antigo em cache) manda 0 tanto para caixa vazia
                # quanto para zero digitado: mantém o comportamento antigo (0 = limpar).
                if val == 0.0 and not zero_explicito:
                    val = None
                incoming[comp] = val

            if not incoming:
                logger.info("company_finance.replace_payments service noop item_id=%s (empty payload)", item_id)
                return item

            # Item inativo não gera NOVOS lançamentos automáticos: bloqueia valor positivo
            # em competência que ainda não possui lançamento. Correções de meses já lançados
            # continuam permitidas (preserva a capacidade de acertar o histórico).
            if not bool(getattr(item, "is_active", True)):
                existing_months = await self._payment_months_for_item(item_id=item_id)
                new_positive = [
                    comp
                    for comp, val in incoming.items()
                    if (val or 0) > 0 and comp not in existing_months
                ]
                if new_positive:
                    meses = ", ".join(month_key(c) for c in sorted(new_positive))
                    raise ValueError(
                        "Cadastro inativo não gera novos lançamentos. "
                        f"Reative o cadastro para lançar novas competências ({meses})."
                    )

            months_in_payload = set(incoming.keys())
            logger.info(
                "company_finance.replace_payments service incoming item_id=%s months=%s values=%s",
                item_id,
                sorted(month_key(c) for c in incoming),
                {month_key(c): v for c, v in incoming.items()},
            )

            # A grade legada (uma caixa por mês) governa o LANÇAMENTO ÚNICO da competência.
            # Atualização IN-PLACE (nunca delete+insert) para preservar o vínculo com o título
            # do CAP (`payable_snapshots.entry_id`) — recriar a linha zeraria o vínculo via
            # ON DELETE SET NULL e desalinharia pagamento/vencimento/descrição do modal.
            # Competências com MÚLTIPLOS lançamentos (geridos no modal) NÃO são achatadas aqui:
            # a caixa da grade passa a ser somente leitura (a soma), e este caminho as ignora.
            inserted = 0
            for comp, val in incoming.items():
                existing = await self._entries_for_month(item_id=item_id, comp=comp)
                if len(existing) > 1:
                    # Preserva os lançamentos do modal; a grade não edita meses com N > 1.
                    logger.info(
                        "company_finance.replace_payments skip multi-entry month item_id=%s comp=%s n=%d",
                        item_id,
                        month_key(comp),
                        len(existing),
                    )
                    continue
                if val is None:
                    for e in existing:  # esvaziar a caixa remove o lançamento → volta à referência
                        await self.db.delete(e)
                elif val > 0:
                    if existing:
                        existing[0].valor = val  # in-place: mantém id/vencimento/descrição
                    else:
                        self.db.add(
                            CompanyFinancialPayment(
                                item_id=item_id,
                                competencia=comp,
                                valor=val,
                                due_date=_default_entry_due(comp),
                                descricao=None,
                            )
                        )
                        inserted += 1
                else:
                    # Zero DECLARADO: o lançamento é PERSISTIDO com 0 — é o que impede a
                    # referência de ser materializada outra vez. O reconciliador do CAP
                    # remove o título aberto da competência.
                    if existing:
                        existing[0].valor = 0
                    else:
                        self.db.add(
                            CompanyFinancialPayment(
                                item_id=item_id,
                                competencia=comp,
                                valor=0,
                                due_date=_default_entry_due(comp),
                                descricao=None,
                            )
                        )
                        inserted += 1
            logger.info(
                "company_finance.replace_payments service upsert item_id=%s inserted=%d",
                item_id,
                inserted,
            )

            item.updated_at = datetime.now(timezone.utc)
            logger.info("company_finance.replace_payments service BEFORE flush item_id=%s", item_id)
            await self.db.flush()
            logger.info("company_finance.replace_payments service AFTER flush item_id=%s", item_id)

            logger.info("company_finance.replace_payments service BEFORE refresh item_id=%s", item_id)
            await self.db.refresh(item, attribute_names=["payments"])
            logger.info("company_finance.replace_payments service AFTER refresh item_id=%s", item_id)

            logger.info(
                "company_finance.replace_payments service BEFORE sync_company_finance_item_months "
                "item_id=%s months=%s",
                item_id,
                sorted(month_key(c) for c in months_in_payload),
            )
            self.last_payable_sync = await self._sync_payables_for_company_finance_item(
                item_id=item_id, months=months_in_payload
            )
            logger.info(
                "company_finance.replace_payments service AFTER sync_company_finance_item_months item_id=%s sync=%s",
                item_id,
                self.last_payable_sync,
            )

            logger.info("company_finance.replace_payments service OK item_id=%s", item_id)
            return item
        except Exception as e:
            logger.error(
                "company_finance.replace_payments service FAILED item_id=%s pagamentos=%s error=%s\n%s",
                item_id,
                pagamentos,
                e,
                traceback.format_exc(),
            )
            raise

    # ------------------------------------------------------------------ #
    # Lançamentos da competência (N por mês) — caminho canônico do modal
    # ------------------------------------------------------------------ #
    async def _entry_snapshot(self, entry_id: UUID) -> PayableSnapshot | None:
        return (
            await self.db.execute(
                select(PayableSnapshot).where(PayableSnapshot.entry_id == entry_id)
            )
        ).scalars().first()

    async def _entry_is_paid(self, snap: PayableSnapshot | None) -> bool:
        if snap is None:
            return False
        if _f(snap.amount_paid) > 0:
            return True
        cnt = await self.db.scalar(
            select(func.count())
            .select_from(PayablePayment)
            .where(
                PayablePayment.payable_snapshot_id == snap.id,
                PayablePayment.reversed_at.is_(None),
            )
        )
        return int(cnt or 0) > 0

    @staticmethod
    def _parse_due(value: object) -> date | None:
        if value is None or value == "":
            return None
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value)[:10])

    async def list_entries(self, *, item_id: UUID, competencia: str) -> dict:
        """Lançamentos de uma competência + status de pagamento (espelho do CAP).

        Fonte de verdade do PAGAMENTO é o Contas a Pagar (por `entry_id`); a grade guarda o
        valor/vencimento/descrição. Cada lançamento traz seu próprio status independente.
        """
        item = await self.db.get(CompanyFinancialItem, item_id)
        if item is None:
            return {"item_id": str(item_id), "competencia": competencia, "lancamentos": [], "total": 0.0}
        comp = parse_month(competencia)
        entries = await self._entries_for_month(item_id=item_id, comp=comp)
        out: list[dict] = []
        total = 0.0
        for e in entries:
            snap = await self._entry_snapshot(e.id)
            paid = await self._entry_is_paid(snap)
            valor = _f(e.valor)
            total += valor
            out.append(
                {
                    "id": str(e.id),
                    "competencia": competencia,
                    "vencimento": e.due_date,
                    "valor": valor,
                    "descricao": e.descricao,
                    "cap_amount_paid": _f(getattr(snap, "amount_paid", 0)) if snap is not None else 0.0,
                    "cap_status": (
                        payable_snapshot_payment_status(
                            amount_paid=snap.amount_paid, amount_final=snap.amount_final
                        )
                        if snap is not None
                        else None
                    ),
                    "has_payment": paid,
                }
            )
        return {
            "item_id": str(item_id),
            "competencia": competencia,
            "lancamentos": out,
            "total": round(total, 2),
        }

    async def replace_entries(
        self, *, item_id: UUID, competencia: str, lancamentos: list[dict]
    ) -> CompanyFinancialItem | None:
        """Substitui o conjunto de LANÇAMENTOS de UMA competência (caminho do modal).

        Genérico para qualquer item de Custo Fixo. Cada lançamento gera/atualiza um título
        independente no CAP (por `entry_id`), com pagamento próprio. Preserva integralmente os
        fluxos atuais:
        - lançamento com pagamento é BLOQUEADO para edição/exclusão (histórico intacto),
          reportado em `skipped_paid`;
        - exclusão de lançamento ABERTO remove o respectivo título; os demais permanecem;
        - a soma da competência (título) continua sendo a única fonte para relatórios/dashboard.
        """
        item = await self.db.get(CompanyFinancialItem, item_id)
        if item is None:
            return None
        if self._uses_schedule(item):
            # Modo 2: os lançamentos são governados pelo Cronograma (fonte única). O modal de
            # competência é somente leitura — toda alteração passa por replace_schedule.
            raise ValueError("Item em modo Cronograma: edite as parcelas pelo Cronograma, não pelo lançamento da competência.")
        await CompanyFinanceCostCenterService(self.db).migrate_legacy_row(item)
        comp = parse_month(competencia)

        existing = {e.id: e for e in await self._entries_for_month(item_id=item_id, comp=comp)}

        # Normaliza a carga: separa por id (edição) e novos.
        incoming_by_id: dict[UUID, dict] = {}
        incoming_new: list[dict] = []
        for raw in lancamentos:
            valor = max(0.0, float(raw.get("valor") or 0))
            payload = {
                "valor": valor,
                "vencimento": self._parse_due(raw.get("vencimento")),
                "descricao": (str(raw.get("descricao")).strip() or None) if raw.get("descricao") else None,
            }
            rid = raw.get("id")
            if rid:
                try:
                    incoming_by_id[UUID(str(rid))] = payload
                except ValueError:
                    incoming_new.append(payload)
            else:
                incoming_new.append(payload)

        # Cadastro inativo não gera NOVOS lançamentos (preserva o ciclo de vida); correções em
        # lançamentos já existentes continuam permitidas.
        if not bool(getattr(item, "is_active", True)):
            has_new_positive = any(p["valor"] > 0 for p in incoming_new) or any(
                rid not in existing and p["valor"] > 0 for rid, p in incoming_by_id.items()
            )
            if has_new_positive and not existing:
                raise ValueError(
                    "Cadastro inativo não gera novos lançamentos. "
                    f"Reative o cadastro para lançar novas competências ({competencia})."
                )

        skipped_paid: list[str] = []

        # 1) Exclusões: existentes ausentes na carga. Bloqueia pagos (preserva histórico).
        keep_ids = set(incoming_by_id.keys())
        for eid, entry in existing.items():
            if eid in keep_ids:
                continue
            snap = await self._entry_snapshot(eid)
            if await self._entry_is_paid(snap):
                skipped_paid.append(competencia)
                continue
            if snap is not None:
                await self.db.delete(snap)  # remove o título ABERTO do CAP
            await self.db.delete(entry)

        # 2) Edições in-place (bloqueia pagos).
        for eid, payload in incoming_by_id.items():
            entry = existing.get(eid)
            if entry is None:
                # id desconhecido: tratado como novo, se positivo.
                if payload["valor"] > 0:
                    incoming_new.append(payload)
                continue
            snap = await self._entry_snapshot(eid)
            if await self._entry_is_paid(snap):
                if _f(entry.valor) != payload["valor"] or entry.due_date != payload["vencimento"]:
                    skipped_paid.append(competencia)
                continue
            if payload["valor"] <= 0:
                # valor não-positivo em edição = exclusão do lançamento aberto.
                if snap is not None:
                    await self.db.delete(snap)
                await self.db.delete(entry)
                continue
            entry.valor = payload["valor"]
            entry.due_date = payload["vencimento"] or _default_entry_due(comp)
            entry.descricao = payload["descricao"]

        # 3) Novos lançamentos (valor positivo).
        for payload in incoming_new:
            if payload["valor"] <= 0:
                continue
            self.db.add(
                CompanyFinancialPayment(
                    item_id=item_id,
                    competencia=comp,
                    valor=payload["valor"],
                    due_date=payload["vencimento"] or _default_entry_due(comp),
                    descricao=payload["descricao"],
                )
            )

        item.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(item, attribute_names=["payments"])

        # Sincroniza a competência com o CAP (cria/atualiza títulos por lançamento).
        sync = await self._sync_payables_for_company_finance_item(item_id=item_id, months={comp})
        # Une avisos de pagamento (exclusão/edição bloqueadas + guarda do reconciliador).
        merged_skipped = list({*(sync.get("skipped_paid") or []), *[parse_month(m) for m in skipped_paid]})
        self.last_payable_sync = {"synced": sync.get("synced", 0), "skipped_paid": merged_skipped}
        return item

    # ------------------------------------------------------------------ #
    # Cronograma Financeiro Personalizado (Endividamento — Modo 2)
    # ------------------------------------------------------------------ #
    @staticmethod
    def preview_ranges(ranges: list[dict]) -> dict:
        """Expande faixas em um cronograma completo (gerador de faixas), sem persistir.

        Cada faixa: {seq_start, seq_end, valor, dia, primeiro_vencimento (date|YYYY-MM-DD)}.
        Delega ao núcleo genérico (`financial_schedule`) — mesma lógica reutilizável por
        qualquer obrigação parcelada no futuro. Não toca banco nem CAP.
        """
        specs: list[RangeSpec] = []
        for r in ranges:
            fdm = r.get("primeiro_vencimento")
            fdm = fdm if isinstance(fdm, date) else date.fromisoformat(str(fdm))
            specs.append(
                RangeSpec(
                    seq_start=int(r["seq_start"]),
                    seq_end=int(r["seq_end"]),
                    amount=Decimal(str(r["valor"])),
                    day=int(r["dia"]),
                    first_due_month=fdm,
                )
            )
        lines = build_schedule(specs)
        return {
            "lines": [
                {"seq": ln.seq, "vencimento": ln.due_date, "valor": float(ln.amount), "descricao": ln.description}
                for ln in lines
            ],
            "count": len(lines),
            "total": float(sum((ln.amount for ln in lines), Decimal("0"))),
        }

    async def list_schedule(self, *, item_id: UUID) -> dict:
        """Cronograma completo do item (todas as parcelas) + espelho de pagamento do CAP.

        Fonte de verdade do PAGAMENTO é o Contas a Pagar (por `entry_id`); o cronograma guarda
        a agenda planejada (data/valor/descrição/seq). Inclui o fechamento vs. valor renegociado.
        """
        item = await self.db.get(CompanyFinancialItem, item_id)
        if item is None:
            return {"item_id": str(item_id), "lines": [], "total_cronograma": 0.0}
        rows = (
            await self.db.execute(
                select(CompanyFinancialPayment)
                .where(CompanyFinancialPayment.item_id == item_id)
                .order_by(
                    CompanyFinancialPayment.schedule_seq.asc().nulls_last(),
                    CompanyFinancialPayment.due_date.asc().nulls_last(),
                    CompanyFinancialPayment.created_at.asc(),
                )
            )
        ).scalars().all()
        lines: list[dict] = []
        core: list[ScheduleLine] = []
        for e in rows:
            snap = await self._entry_snapshot(e.id)
            paid = await self._entry_is_paid(snap)
            lines.append(
                {
                    "id": str(e.id),
                    "seq": e.schedule_seq,
                    "vencimento": e.due_date,
                    "valor": _f(e.valor),
                    "descricao": e.descricao,
                    "cap_amount_paid": _f(getattr(snap, "amount_paid", 0)) if snap is not None else 0.0,
                    "cap_status": (
                        payable_snapshot_payment_status(amount_paid=snap.amount_paid, amount_final=snap.amount_final)
                        if snap is not None
                        else None
                    ),
                    "has_payment": paid,
                }
            )
            core.append(ScheduleLine(seq=e.schedule_seq or 0, due_date=e.due_date or item.start_date, amount=Decimal(str(e.valor))))
        negociado = item.renegotiated_amount if item.renegotiated_amount is not None else 0
        closure = validate_closure(negociado, core)
        return {
            "item_id": str(item_id),
            "uses_custom_schedule": bool(getattr(item, "uses_custom_schedule", False)),
            "renegotiated_amount": _f(item.renegotiated_amount) if item.renegotiated_amount is not None else None,
            "total_cronograma": float(closure.total_cronograma),
            "diferenca": float(closure.diferenca),
            "is_valid": closure.is_valid,
            "data_encerramento": max((e.due_date for e in rows if e.due_date), default=None),
            "lines": lines,
        }

    async def replace_schedule(
        self, *, item_id: UUID, lines: list[dict], allow_unbalanced: bool = False
    ) -> CompanyFinancialItem | None:
        """Substitui o CRONOGRAMA completo do item (Modo 2). Fonte única da execução da dívida.

        Cada linha (parcela) é um lançamento `company_financial_payments` que gera um título no
        CAP por `entry_id` (pipeline existente dos múltiplos lançamentos). Regras:
        - fechamento: Σ cronograma deve igualar o valor renegociado (bloqueia salvar, salvo
          `allow_unbalanced`);
        - parcela PAGA é imutável e nunca é excluída (histórico preservado); tentativa de alterar/
          remover é reportada em `skipped_paid` e a parcela permanece intacta;
        - casamento por `id` (edição) e, na ausência, por `seq` (regeração por faixas preserva as
          pagas); parcela aberta é atualizada in-place (preserva o vínculo do título);
        - toda alteração passa pelo cronograma; o CAP é sincronizado automaticamente (nunca editado
          manualmente para representar parcelas).
        """
        item = await self.db.get(CompanyFinancialItem, item_id)
        if item is None:
            return None
        if item.tipo != "endividamento" or not bool(getattr(item, "uses_custom_schedule", False)):
            raise ValueError("Cronograma disponível apenas para endividamento em modo cronograma.")
        if not bool(item.has_renegotiation) or item.renegotiated_amount is None:
            raise ValueError("Defina a renegociação (valor renegociado) antes de montar o cronograma.")
        await CompanyFinanceCostCenterService(self.db).migrate_legacy_row(item)

        # Normaliza a carga.
        incoming: list[dict] = []
        seen_seq: set[int] = set()
        for raw in lines:
            seq = int(raw["seq"])
            if seq in seen_seq:
                raise ValueError(f"Sequência de parcela duplicada no cronograma: {seq}.")
            seen_seq.add(seq)
            venc = self._parse_due(raw.get("vencimento"))
            if venc is None:
                raise ValueError(f"Parcela {seq}: vencimento é obrigatório.")
            valor = round(max(0.0, float(raw.get("valor") or 0)), 2)
            if valor <= 0:
                raise ValueError(f"Parcela {seq}: valor deve ser maior que zero.")
            desc = (str(raw.get("descricao")).strip() or None) if raw.get("descricao") else None
            rid_raw = raw.get("id")
            try:
                rid = UUID(str(rid_raw)) if rid_raw else None
            except ValueError:
                rid = None
            incoming.append({"id": rid, "seq": seq, "vencimento": venc, "valor": valor, "descricao": desc})

        # Fechamento (Σ cronograma == renegociado).
        core = [ScheduleLine(seq=i["seq"], due_date=i["vencimento"], amount=Decimal(str(i["valor"]))) for i in incoming]
        closure = validate_closure(item.renegotiated_amount, core)
        if not closure.is_valid and not allow_unbalanced:
            raise ValueError(
                "O cronograma não fecha o valor renegociado. "
                f"Diferença: R$ {closure.diferenca}. Ajuste as parcelas para fechar o total."
            )

        existing_rows = (
            await self.db.execute(
                select(CompanyFinancialPayment).where(CompanyFinancialPayment.item_id == item_id)
            )
        ).scalars().all()
        by_id = {e.id: e for e in existing_rows}
        by_seq = {e.schedule_seq: e for e in existing_rows if e.schedule_seq is not None}
        paid_map: dict[UUID, bool] = {}
        for e in existing_rows:
            paid_map[e.id] = await self._entry_is_paid(await self._entry_snapshot(e.id))

        affected_months: set[date] = {e.competencia for e in existing_rows}
        skipped_paid: list[date] = []
        matched_ids: set[UUID] = set()

        for line in incoming:
            comp = first_of_month(line["vencimento"])
            affected_months.add(comp)
            entry = by_id.get(line["id"]) if line["id"] else by_seq.get(line["seq"])
            if entry is not None:
                matched_ids.add(entry.id)
                if paid_map.get(entry.id):
                    # Parcela paga é imutável: preserva intacta; reporta se houve tentativa de mudar.
                    if _f(entry.valor) != line["valor"] or entry.due_date != line["vencimento"]:
                        skipped_paid.append(entry.competencia)
                    if entry.schedule_seq is None:
                        entry.schedule_seq = line["seq"]
                    continue
                old_comp = entry.competencia
                if old_comp != comp:
                    # Parcela aberta mudou de competência: remove o título antigo (o novo é
                    # recriado pela sincronização no mês de destino). Preserva o entry_id do
                    # lançamento (movido, não recriado).
                    affected_months.add(old_comp)
                    old_snap = await self._entry_snapshot(entry.id)
                    if old_snap is not None:
                        await self.db.delete(old_snap)
                entry.competencia = comp
                entry.valor = line["valor"]
                entry.due_date = line["vencimento"]
                entry.descricao = line["descricao"]
                entry.schedule_seq = line["seq"]
            else:
                self.db.add(
                    CompanyFinancialPayment(
                        item_id=item_id,
                        competencia=comp,
                        valor=line["valor"],
                        due_date=line["vencimento"],
                        descricao=line["descricao"],
                        schedule_seq=line["seq"],
                    )
                )

        # Parcelas existentes não representadas na carga.
        for e in existing_rows:
            if e.id in matched_ids:
                continue
            if paid_map.get(e.id):
                # Nunca perde histórico: parcela paga é preservada mesmo se ausente na carga.
                skipped_paid.append(e.competencia)
                continue
            snap = await self._entry_snapshot(e.id)
            if snap is not None:
                await self.db.delete(snap)  # remove o título ABERTO do CAP
            await self.db.delete(e)

        item.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(item, attribute_names=["payments"])

        sync = await self._sync_payables_for_company_finance_item(item_id=item_id, months=affected_months)

        # Limpeza de RESÍDUOS do modo legado (obrigatório mensal): no Modo cronograma o
        # cronograma é a ÚNICA fonte de títulos. Remove títulos de dívida ABERTOS do item que
        # NÃO pertencem ao cronograma atual — inclusive órfãos com entry_id NULL, gerados pela
        # replicação automática antiga em meses fora do cronograma. Preserva pagos (histórico).
        current_entry_ids = {
            row[0]
            for row in (
                await self.db.execute(
                    select(CompanyFinancialPayment.id).where(CompanyFinancialPayment.item_id == item_id)
                )
            ).all()
        }
        stray_titles = (
            await self.db.execute(
                select(PayableSnapshot).where(
                    PayableSnapshot.ref_id == item_id,
                    PayableSnapshot.type == PayableSnapshotType.ENDIVIDAMENTO,
                    PayableSnapshot.project_id.is_(None),
                )
            )
        ).scalars().all()
        removed_stray = 0
        for snap in stray_titles:
            if snap.entry_id is not None and snap.entry_id in current_entry_ids:
                continue  # título válido de uma parcela do cronograma
            if await self._entry_is_paid(snap):
                continue  # histórico: nunca remove título com pagamento
            await self.db.delete(snap)
            removed_stray += 1
        if removed_stray:
            await self.db.flush()

        merged_skipped = list({*(sync.get("skipped_paid") or []), *skipped_paid})
        self.last_payable_sync = {
            "synced": sync.get("synced", 0),
            "skipped_paid": merged_skipped,
            "closure": {
                "renegotiated_amount": float(closure.total_negociado),
                "total_cronograma": float(closure.total_cronograma),
                "diferenca": float(closure.diferenca),
                "is_valid": closure.is_valid,
            },
        }
        return item

    # ------------------------------------------------------------------ #
    # LEITURA — Fonte ÚNICA da execução da dívida (Modo 2). Todo indicador
    # (saldo/progresso/pago/restante/parcelas/pendências/KPIs/gráficos) deriva
    # de UM cálculo oficial: núcleo genérico `compute_indicators` alimentado por
    # cronograma (planejado) + pagamentos REAIS do CAP (via entry_id). Nunca
    # infere pagamento a partir da existência da parcela.
    # ------------------------------------------------------------------ #
    @staticmethod
    def _uses_schedule(it: CompanyFinancialItem) -> bool:
        return getattr(it, "tipo", None) == "endividamento" and bool(getattr(it, "uses_custom_schedule", False))

    async def _cap_paid_by_entry(self, item_ids: list[UUID]) -> dict[UUID, float]:
        """Pago REAL por PARCELA: `payable_snapshots.amount_paid` do título vinculado (entry_id)."""
        if not item_ids:
            return {}
        rows = (
            await self.db.execute(
                select(PayableSnapshot.entry_id, PayableSnapshot.amount_paid).where(
                    PayableSnapshot.ref_id.in_(item_ids),
                    PayableSnapshot.type == PayableSnapshotType.ENDIVIDAMENTO,
                    PayableSnapshot.entry_id.is_not(None),
                )
            )
        ).all()
        out: dict[UUID, float] = {}
        for entry_id, amount_paid in rows:
            out[entry_id] = out.get(entry_id, 0.0) + _f(amount_paid)
        return out

    async def _cap_paid_by_month(self, item_ids: list[UUID]) -> dict[UUID, dict[date, float]]:
        """Pagamentos REAIS do CAP por (item, mês do pagamento) — fluxo de caixa (KPIs/gráfico)."""
        if not item_ids:
            return {}
        rows = (
            await self.db.execute(
                select(PayableSnapshot.ref_id, PayablePayment.payment_date, PayablePayment.amount)
                .join(PayablePayment, PayablePayment.payable_snapshot_id == PayableSnapshot.id)
                .where(
                    PayableSnapshot.ref_id.in_(item_ids),
                    PayableSnapshot.type == PayableSnapshotType.ENDIVIDAMENTO,
                    PayablePayment.reversed_at.is_(None),
                )
            )
        ).all()
        out: dict[UUID, dict[date, float]] = {}
        for ref_id, pdate, amount in rows:
            m = first_of_month(pdate)
            bucket = out.setdefault(ref_id, {})
            bucket[m] = bucket.get(m, 0.0) + _f(amount)
        return out

    async def auto_close_settled_schedule(self, *, item_id: UUID) -> bool:
        """Cronograma QUITADO → inativa o cadastro, com encerramento no MÊS SEGUINTE.

        Dívida paga até a última parcela não deveria continuar na lista de ativos: ela não gera
        mais título (Modo 2 só gera onde há parcela), mas polui a tela de quem procura o que
        ainda está em curso.

        O encerramento é datado no PRIMEIRO DIA DO MÊS SEGUINTE — nunca no mês corrente. Isso
        preserva duas coisas ao mesmo tempo: a competência atual segue dentro da vigência (então
        nenhum título dela vira resíduo), e o item continua visível no filtro "Ativos" até a
        virada, quando some sozinho.

        Não faz nada quando: o item não está em Modo 2, já está inativo, ainda tem saldo, ou não
        tem nenhuma parcela. Idempotente — chamar de novo não muda nada.
        """
        item = (
            await self.db.execute(
                select(CompanyFinancialItem)
                .options(selectinload(CompanyFinancialItem.payments))
                .where(CompanyFinancialItem.id == item_id)
            )
        ).scalar_one_or_none()
        if item is None:
            return False
        if not bool(getattr(item, "uses_custom_schedule", False)):
            return False
        if not bool(getattr(item, "is_active", True)):
            return False
        if not item.payments:
            return False

        pbe = await self._cap_paid_by_entry([item.id])
        ind = self._schedule_execution(item, pbe)
        if float(ind.saldo_restante) > 0.005 or int(ind.parcelas_restantes) > 0:
            return False

        hoje = date.today()
        item.is_active = False
        item.end_date = next_competencia(first_of_month(hoje))
        item.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        logger.info(
            "company_finance auto-close settled schedule item_id=%s nome=%s end_date=%s",
            item.id,
            item.nome,
            item.end_date,
        )
        return True

    def _schedule_execution(self, it: CompanyFinancialItem, paid_by_entry: dict[UUID, float]):
        """CÁLCULO OFICIAL ÚNICO da execução da dívida em Modo 2.

        Monta as parcelas (planejadas) e o pago real por parcela (CAP via entry_id) e delega ao
        núcleo genérico `compute_indicators`. É a ÚNICA fonte de saldo/progresso/pago/restante/
        parcelas/próxima/última/encerramento — reutilizável por qualquer obrigação parcelada.
        """
        lines: list[ScheduleLine] = []
        paid_by_seq: dict[int, float] = {}
        for p in it.payments:
            seq = p.schedule_seq if p.schedule_seq is not None else 0
            lines.append(
                ScheduleLine(seq=seq, due_date=p.due_date or it.start_date, amount=Decimal(str(p.valor)))
            )
            paid_by_seq[seq] = paid_by_seq.get(seq, 0.0) + paid_by_entry.get(p.id, 0.0)
        negociado = it.renegotiated_amount if it.renegotiated_amount is not None else 0
        return compute_indicators(total_negociado=negociado, lines=lines, paid_by_seq=paid_by_seq)

    @staticmethod
    def _schedule_execution_dict(ind) -> dict:
        """Serializa os indicadores oficiais para o contrato de leitura (frontend só exibe)."""
        return {
            "total_negociado": float(ind.total_negociado),
            "total_cronograma": float(ind.total_cronograma),
            "total_pago": float(ind.total_pago),
            "saldo_restante": float(ind.saldo_restante),
            "progresso": round(float(ind.progresso), 6),
            "parcelas_total": ind.parcelas_total,
            "parcelas_pagas": ind.parcelas_pagas,
            "parcelas_restantes": ind.parcelas_restantes,
            "proxima_vencimento": ind.proxima_parcela.due_date if ind.proxima_parcela else None,
            "proxima_valor": float(ind.proxima_parcela.amount) if ind.proxima_parcela else None,
            "ultima_vencimento": ind.ultima_parcela.due_date if ind.ultima_parcela else None,
            "data_encerramento": ind.data_encerramento,
        }

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
        sched_ids = [it.id for it in items if self._uses_schedule(it)]
        pbe_all = await self._cap_paid_by_entry(sched_ids)
        pbm_all = await self._cap_paid_by_month(sched_ids)
        total_pago_mes = 0.0
        saldo_restante = 0.0
        for it in items:
            if self._uses_schedule(it):
                # Fonte única: saldo do cálculo oficial; pago do mês = pagamento REAL do CAP.
                ind = self._schedule_execution(it, pbe_all)
                saldo_restante += float(ind.saldo_restante)
                total_pago_mes += round(pbm_all.get(it.id, {}).get(comp, 0.0), 2)
            else:
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
                    .options(
                selectinload(CompanyFinancialItem.payments),
                selectinload(CompanyFinancialItem.employee),
                selectinload(CompanyFinancialItem.cost_center_project),
            )
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
        # Múltiplos lançamentos: soma TODOS os lançamentos da competência (não só o primeiro).
        total_pago_mes = 0.0
        for it in items:
            total_pago_mes += sum(_f(p.valor) for p in it.payments if p.competencia == comp)
        return {
            "total_esperado_mes": total_esperado_mes,
            "total_pago_mes": total_pago_mes,
            "quantidade_itens": len(items),
        }

    def _renegotiation_anchor_month(self, it: CompanyFinancialItem) -> date | None:
        """Primeiro-de-mês da 1ª parcela da renegociação.

        Prioridade: data do 1º pagamento → competência mais antiga já lançada →
        data do acordo → mês de criação do item. Para dados legados sem datas,
        ancora no mês de criação (dia de vencimento default tratado à parte).
        """
        fpd = getattr(it, "renegotiation_first_payment_date", None)
        if fpd is not None:
            return first_of_month(fpd)
        if it.payments:
            return min(p.competencia for p in it.payments)
        agr = getattr(it, "renegotiation_agreement_date", None)
        if agr is not None:
            return first_of_month(agr)
        created = getattr(it, "created_at", None)
        if created is not None:
            return first_of_month(created.date() if hasattr(created, "date") else created)
        return None

    def _renegotiation_parcela_value(self, it: CompanyFinancialItem) -> float:
        """Valor previsto da parcela: installment_value (parcelado) ou saldo renegociado (única)."""
        rt = getattr(it, "renegotiation_type", None)
        rt_val = getattr(rt, "value", rt)
        if rt_val == "INSTALLMENTS" and getattr(it, "installment_value", None) is not None:
            return _f(it.installment_value)
        return _debt_base_amount(it)

    async def pendencias(self, tipo: str, competencia: str) -> dict:
        """Pendências de lançamento (obrigatoriedades sem valor na competência).

        Apenas monitoramento operacional — não cria lançamento, conta a pagar
        ou título com valor zero. As obrigatoriedades de uma competência são:
        - manuais: itens com `is_monthly_required` (ambos os tipos);
        - automáticas (endividamento): renegociações com parcela prevista no mês,
          enquanto não quitadas.
        Retorna também os totais previsto/pago das obrigatoriedades no mês.
        """
        comp = parse_month(competencia)
        # Cadastros inativos não geram novas obrigatoriedades/pendências (regra do ciclo
        # de vida). O histórico já lançado permanece intacto em contas a pagar.
        where = [CompanyFinancialItem.tipo == tipo, CompanyFinancialItem.is_active.is_(True)]
        if tipo == "endividamento":
            where.append(
                CompanyFinancialItem.is_monthly_required.is_(True)
                | CompanyFinancialItem.has_renegotiation.is_(True)
            )
        else:
            where.append(CompanyFinancialItem.is_monthly_required.is_(True))

        items = (
            (
                await self.db.execute(
                    select(CompanyFinancialItem)
                    .where(*where)
                    .options(
                        selectinload(CompanyFinancialItem.payments),
                        selectinload(CompanyFinancialItem.employee),
                        selectinload(CompanyFinancialItem.cost_center_project),
                    )
                    .order_by(CompanyFinancialItem.nome)
                )
            )
            .scalars()
            .unique()
            .all()
        )

        pendencias: list[dict] = []
        total_previsto = 0.0
        total_pago = 0.0
        # Modo 2: pago REAL do CAP (fonte única) para decidir a quitação das parcelas do mês.
        sched_ids = [it.id for it in items if self._uses_schedule(it)]
        pbe_all = await self._cap_paid_by_entry(sched_ids)
        pbm_all = await self._cap_paid_by_month(sched_ids)
        for it in items:
            # Modo 2 (Cronograma): pendência = parcela vencendo no mês cujo título do CAP não
            # está quitado. "Pago" vem SEMPRE do CAP (nunca da existência da parcela planejada).
            if self._uses_schedule(it):
                parcels = [p for p in it.payments if p.competencia == comp]
                if not parcels:
                    continue  # sem parcela do cronograma neste mês → sem obrigatoriedade
                valor_previsto = round(sum(_f(p.valor) for p in parcels), 2)
                paid_real = round(sum(pbe_all.get(p.id, 0.0) for p in parcels), 2)
                total_previsto += valor_previsto
                total_pago += paid_real
                if paid_real >= valor_previsto:
                    continue  # parcela(s) do mês já quitada(s) no CAP → não é pendência
                read = await self._item_to_read(
                    it, comp, schedule_paid_by_entry=pbe_all, schedule_paid_by_month=pbm_all.get(it.id, {})
                )
                pendencias.append(
                    {
                        "item_id": it.id,
                        "nome": it.nome,
                        "competencia": competencia,
                        "category": read.get("category"),
                        "cost_center": read.get("cost_center"),
                        "valor_referencia": valor_previsto,
                        "ultimo_valor": None,
                        "ultimo_mes": None,
                        "origem": "cronograma",
                    }
                )
                continue
            # Define se o item é obrigatoriedade nesta competência e o valor previsto.
            is_auto = False
            valor_previsto: float
            if tipo == "endividamento" and bool(getattr(it, "has_renegotiation", False)):
                anchor = self._renegotiation_anchor_month(it)
                count = renegotiation_installment_count(
                    renegotiation_type=getattr(it, "renegotiation_type", None),
                    installment_count=getattr(it, "installment_count", None),
                )
                total_pago_item = sum(_f(p.valor) for p in it.payments)
                quitado = total_pago_item >= _debt_base_amount(it) and _debt_base_amount(it) > 0
                if (
                    anchor is not None
                    and not quitado
                    and parcela_prevista_na_competencia(
                        anchor_month=anchor, installment_count=count, competencia=comp
                    )
                ):
                    is_auto = True
                    valor_previsto = self._renegotiation_parcela_value(it)
                elif bool(getattr(it, "is_monthly_required", False)):
                    valor_previsto = _f(it.valor_referencia)
                else:
                    continue  # renegociação sem parcela neste mês e não-manual
            elif bool(getattr(it, "is_monthly_required", False)):
                read = await self._item_to_read(it, comp)
                valor_previsto = float(read.get("valor_referencia", 0.0))
            else:
                continue

            # Múltiplos lançamentos: soma TODOS os lançamentos da competência.
            pago_mes = sum(_f(p.valor) for p in it.payments if p.competencia == comp)
            total_previsto += valor_previsto
            total_pago += pago_mes

            if pago_mes > 0:
                continue  # já lançado → não é pendência (mas conta nos totais)

            last = last_known_payment([(p.competencia, _f(p.valor)) for p in it.payments], comp)
            read = await self._item_to_read(it, comp)
            pendencias.append(
                {
                    "item_id": it.id,
                    "nome": it.nome,
                    "competencia": competencia,
                    "category": read.get("category"),
                    "cost_center": read.get("cost_center"),
                    "valor_referencia": round(valor_previsto, 2),
                    "ultimo_valor": last[1] if last is not None else None,
                    "ultimo_mes": month_key(last[0]) if last is not None else None,
                    "origem": "renegociacao" if is_auto else "manual",
                }
            )

        return {
            "competencia": competencia,
            "quantidade": len(pendencias),
            "pendencias": pendencias,
            "total_previsto": round(total_previsto, 2),
            "total_pago": round(total_pago, 2),
        }

    async def pendencias_custos_fixos(self, competencia: str) -> dict:
        """Compat: pendências de custos fixos (delega à implementação genérica)."""
        return await self.pendencias("custo_fixo", competencia)

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

        # Modo 2: pagamentos REAIS do CAP por mês (fonte única) para timeline/saldo.
        sched_ids = [it.id for it in items if self._uses_schedule(it)]
        pbm_all = await self._cap_paid_by_month(sched_ids)

        points: list[dict] = []
        for m in months:
            mk = month_key(m)
            # Múltiplos lançamentos: soma TODOS os lançamentos da competência (Modo 1);
            # Modo 2: pagamento REAL do CAP no mês (nunca a parcela planejada).
            pagamentos_mes = 0.0
            for it in items:
                if self._uses_schedule(it):
                    pagamentos_mes += round(pbm_all.get(it.id, {}).get(m, 0.0), 2)
                else:
                    pagamentos_mes += sum(_f(p.valor) for p in it.payments if p.competencia == m)

            saldo_restante_total = None
            if tipo == "endividamento":
                saldo_restante_total = 0.0
                for it in items:
                    ref = _debt_base_amount(it)
                    if self._uses_schedule(it):
                        cum = sum(v for mm, v in pbm_all.get(it.id, {}).items() if mm <= m)
                    else:
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
