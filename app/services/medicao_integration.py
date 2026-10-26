"""Integração com o sistema de Medição (Fiscalização AT): dados do mês para a margem por colaborador.

Somente leitura. O Medição calcula a margem de cada colaborador (faturamento Enel − custos) e busca aqui
o que só o SGC sabe:

- impostos e antecipação do projeto no mês (mesmas regras do Dashboard operacional), como taxa sobre a
  receita — o Medição aplica a taxa ao faturamento de cada colaborador;
- custo de veículos do projeto rateado pelos condutores (`vehicles.driver_employee_id`), com peso no custo
  mensal de cada veículo ativo no mês; veículo sem condutor fica em `unassigned`;
- folha PAGA no Contas a Pagar por colaborador (a folha do mês M é paga no CAP de M+1), inclusive os
  componentes variáveis do projeto. Só é "real" quando o mês do pagamento já fechou — mesma regra do Dashboard.

Acesso por chave de integração (header `X-Integration-Key`), sem usuário: ver `app/modules/integrations`.
"""

from __future__ import annotations

import hashlib
import hmac
from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scenario import Scenario
from app.models.employee import Employee
from app.models.fleet import Vehicle
from app.models.payable_snapshot import PayableOrigin, PayableSnapshot, PayableSnapshotType
from app.models.payment_component import PaymentVariableComponent
from app.models.project import Project
from app.models.project_operational import ProjectLabor
from app.services.company_costs import vehicle_in_fleet
from app.services.company_finance_rules import month_bounds
from app.services.financial_service import FinancialService
from app.utils.date_utils import next_competencia, normalize_competencia


# --------------------------------------------------------------------------- #
# Chave de integração
# --------------------------------------------------------------------------- #
def key_matches(provided: str | None, expected_sha256: str | None) -> bool:
    """Compara a chave recebida com o SHA-256 configurado, em tempo constante. Sem configuração = fechado."""
    expected = (expected_sha256 or "").strip().lower()
    if not expected or not provided:
        return False
    digest = hashlib.sha256(provided.strip().encode()).hexdigest()
    return hmac.compare_digest(digest, expected)


def allowed_projects(raw: str | None) -> set[str]:
    return {x.strip().lower() for x in (raw or "").split(",") if x.strip()}


# --------------------------------------------------------------------------- #
# Regras puras
# --------------------------------------------------------------------------- #
def project_key(project) -> str:
    return ((getattr(project, "cost_center", None) or "").strip() or (project.name or "").strip()).casefold()


def allocate_vehicles(
    vehicles: Iterable, *, comp: date, project_cost_center: str, total: float
) -> tuple[dict[UUID, dict], float]:
    """Rateia o custo de veículos do projeto no mês pelos veículos ativos do centro de custo do projeto,
    com peso no custo mensal de cada um. Devolve ({condutor: {amount, plates}}, parte sem condutor)."""
    start, end = month_bounds(comp)
    frota = [
        v for v in vehicles
        if vehicle_in_fleet(v, start=start, end=end) and (v.cost_center or "").strip().casefold() == project_cost_center
    ]
    peso_total = sum(float(v.monthly_cost) for v in frota)
    por_condutor: dict[UUID, dict] = {}
    sem_condutor = 0.0
    if peso_total <= 0 or total <= 0:
        return por_condutor, (total if total > 0 else 0.0)
    for v in frota:
        parte = total * float(v.monthly_cost) / peso_total
        if v.driver_employee_id is None:
            sem_condutor += parte
            continue
        linha = por_condutor.setdefault(v.driver_employee_id, {"amount": 0.0, "plates": []})
        linha["amount"] += parte
        linha["plates"].append(v.plate)
    return por_condutor, sem_condutor


def labor_paid_by_employee(rows: Iterable, variable_employee: dict[UUID, UUID]) -> dict[UUID, dict]:
    """Soma o CAP de Colaborador por pessoa. `rows`: títulos (ref_id, origin, name, amount_final, amount_paid);
    componente variável (origin VARIABLE) tem ref_id = componente → `variable_employee` leva ao colaborador."""
    out: dict[UUID, dict] = defaultdict(lambda: {"amount_paid": 0.0, "amount_final": 0.0, "components": []})
    for r in rows:
        employee_id = variable_employee.get(r.ref_id) if r.origin == PayableOrigin.VARIABLE.value else r.ref_id
        if employee_id is None:
            continue
        linha = out[employee_id]
        linha["amount_paid"] += float(r.amount_paid or 0)
        linha["amount_final"] += float(r.amount_final or 0)
        partes = str(r.name).split(" — ", 1)          # "Nome — Componente"; título só com o nome = pagamento do mês
        componente = partes[1] if len(partes) == 2 else "Pagamento do mês"
        linha["components"].append({"name": componente, "amount_paid": float(r.amount_paid or 0),
                                    "amount_final": float(r.amount_final or 0)})
    return dict(out)


def _ratio(part: float, whole: float) -> float:
    return float(part) / float(whole) if whole else 0.0


# --------------------------------------------------------------------------- #
# Consultas
# --------------------------------------------------------------------------- #
class MedicaoIntegrationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def project(self, project_id: UUID) -> Project | None:
        return await self.session.get(Project, project_id)

    async def employees(self, project: Project) -> list[dict]:
        """Colaboradores que já tiveram mão de obra lançada no projeto (para o vínculo no Medição)."""
        ids = select(ProjectLabor.employee_id).where(ProjectLabor.project_id == project.id)
        rows = (
            await self.session.execute(
                select(Employee).where(Employee.id.in_(ids)).order_by(Employee.full_name)
            )
        ).scalars().all()
        return [
            {"id": str(e.id), "full_name": e.full_name, "email": e.email,
             "employment_type": e.employment_type, "is_active": bool(e.is_active)}
            for e in rows
        ]

    async def month(self, project: Project, competencia: date, *, today: date | None = None) -> dict:
        comp = normalize_competencia(competencia)
        today = today or date.today()
        fin = FinancialService(self.session)
        c = await fin.calcular_consolidado_projeto(project_id=project.id, competencia=comp, scenario=Scenario.REALIZADO)
        receita = float(c["revenue_total"] or 0)

        vehicles = (await self.session.execute(select(Vehicle))).scalars().all()
        por_condutor, sem_condutor = allocate_vehicles(
            vehicles, comp=comp, project_cost_center=project_key(project), total=float(c["vehicle_cost"] or 0)
        )

        pay_month = next_competencia(comp)
        titulos = (
            await self.session.execute(
                select(PayableSnapshot).where(
                    PayableSnapshot.month == pay_month,
                    PayableSnapshot.type == PayableSnapshotType.COLLABORATOR,
                    PayableSnapshot.project_id == project.id,
                    PayableSnapshot.is_obsolete.is_(False),
                    PayableSnapshot.include_in_dashboard.is_(True),
                )
            )
        ).scalars().all()
        variaveis = [t.ref_id for t in titulos if t.origin == PayableOrigin.VARIABLE.value and t.ref_id]
        variable_employee = (
            dict((await self.session.execute(
                select(PaymentVariableComponent.id, PaymentVariableComponent.employee_id)
                .where(PaymentVariableComponent.id.in_(variaveis))
            )).all())
            if variaveis else {}
        )
        pagos = labor_paid_by_employee(titulos, variable_employee)
        fechado = pay_month < today.replace(day=1)

        return {
            "project": {"id": str(project.id), "name": project.name, "contract_number": project.contract_number},
            "competencia": comp.isoformat(),
            "revenue": receita,
            "taxes": {
                "amount": float(c["tax_amount"] or 0), "rate": _ratio(c["tax_amount"], receita),
                "regime": c.get("tax_regime"),
                "parts": {k: float(c.get(f"tax_{k}") or 0) for k in ("pis", "cofins", "iss", "irpj", "csll")},
            },
            "anticipation": {
                "rate": float(c["anticipation_rate_used"] or 0), "source": c.get("anticipation_source"),
                "partial": bool(c.get("anticipation_partial")), "amount": float(c["anticipation_amount"] or 0),
            },
            "retention_amount": float(c["total_retention"] or 0),
            "vehicles": {
                "total": float(c["vehicle_cost"] or 0), "real": bool(c.get("vehicle_real")),
                "by_employee": [{"employee_id": str(k), "amount": round(v["amount"], 2), "plates": sorted(v["plates"])}
                                for k, v in por_condutor.items()],
                "unassigned": round(sem_condutor, 2),
            },
            "labor": {
                "pay_month": pay_month.isoformat(), "closed": fechado,
                "by_employee": [{"employee_id": str(k), "amount_paid": round(v["amount_paid"], 2),
                                 "amount_final": round(v["amount_final"], 2), "components": v["components"]}
                                for k, v in pagos.items()],
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
