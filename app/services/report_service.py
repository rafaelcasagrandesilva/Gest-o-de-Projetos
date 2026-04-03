from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.user import User
from app.schemas.dashboard import DirectorSummary, FinancialDashboardSummary, MonthlyPoint
from app.services.company_finance_service import CompanyFinanceService
from app.services.dashboard_service import DashboardService
from app.services.employees_service import EmployeesService, default_cost_reference
from app.services.fleet_service import FleetService, fleet_vehicle_to_read
from app.services.project_structure_service import ProjectStructureService
from app.services.projects_service import ProjectsService
from app.services.financial_crud_service import FinancialCrudService
from app.services.receivable_service import ReceivableService
from app.services.users_service import UsersService
from app.utils.date_utils import normalize_competencia


def _uuid(filters: dict[str, Any], key: str) -> UUID | None:
    raw = filters.get(key)
    if raw is None or raw == "":
        return None
    if isinstance(raw, UUID):
        return raw
    return UUID(str(raw))


def _competencia_date(filters: dict[str, Any], key: str = "competencia") -> date | None:
    raw = filters.get(key)
    if raw is None or raw == "":
        return None
    if isinstance(raw, date):
        return normalize_competencia(raw)
    s = str(raw).strip()
    if len(s) >= 10 and s[4] == "-":
        y, m, d = int(s[0:4]), int(s[5:7]), int(s[8:10])
        return date(y, m, d)
    if len(s) == 7 and s[4] == "-":
        y, m = int(s[0:4]), int(s[5:7])
        return date(y, m, 1)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key} inválido (use YYYY-MM).")


class ReportService:
    """Monta dados estruturados para relatórios (sem renderização)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def generate_project_summary(self, *, project_id: UUID, competencia: date) -> dict[str, Any]:
        comp = normalize_competencia(competencia)
        proj = await self.session.get(Project, project_id)
        if not proj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado.")
        dash = DashboardService(self.session)
        pst = ProjectStructureService(self.session)
        summary = await dash.resumo_por_projeto(project_id=project_id, competencia=comp)
        labor = await pst.list_labor_details(project_id=project_id, competencia=comp)
        vehicles = await pst.list_project_vehicles_read(project_id=project_id, competencia=comp)
        systems = await pst.list_systems(project_id=project_id, competencia=comp)
        fixed = await pst.list_fixed(project_id=project_id, competencia=comp)
        return {
            "project_name": proj.name,
            "competencia": comp.isoformat(),
            "summary": summary,
            "labor": [x.model_dump(mode="json") for x in labor],
            "vehicles": [x.model_dump(mode="json") for x in vehicles],
            "systems": [
                {"id": str(x.id), "name": x.name, "value": float(x.value)} for x in systems
            ],
            "fixed_operational": [
                {"id": str(x.id), "name": x.name, "value": float(x.value)} for x in fixed
            ],
        }

    async def generate_company_summary(
        self, *, competencia: date, project_ids: list[UUID]
    ) -> dict[str, Any]:
        comp = normalize_competencia(competencia)
        dash = DashboardService(self.session)
        rows = await dash.list_projects_financial_summaries(competencia=comp, project_ids=project_ids)
        return {"competencia": comp.isoformat()[:7], "rows": rows}

    async def generate_employees_report(self, *, competencia: date | None) -> dict[str, Any]:
        comp = competencia or default_cost_reference()
        rows = await EmployeesService(self.session).list_employees_as_read(
            offset=0, limit=10_000, competencia=comp
        )
        return {
            "competencia_ref": comp.isoformat(),
            "rows": [
                {
                    "nome": e.full_name,
                    "tipo": e.employment_type,
                    "custo": float(e.total_cost or 0),
                }
                for e in rows
            ],
        }

    async def generate_vehicles_report(self, *, active_only: bool) -> dict[str, Any]:
        rows = await FleetService(self.session).list_vehicles(
            offset=0, limit=10_000, active_only=active_only
        )
        out = []
        for r in rows:
            v = fleet_vehicle_to_read(r)
            out.append(
                {
                    "placa": v.plate,
                    "tipo": v.vehicle_type,
                    "custo_mensal": float(v.monthly_cost or 0),
                    "ativo": v.is_active,
                }
            )
        return {"active_only": active_only, "rows": out}

    async def generate_invoices_report(
        self,
        *,
        project_id: UUID | None,
        status_filter: str | None,
        year: int | None,
        month: int | None,
    ) -> dict[str, Any]:
        if (year is None) != (month is None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Informe ano e mês juntos para o período, ou deixe ambos vazios.",
            )
        svc = ReceivableService(self.session)
        invs = await svc.list_invoices(
            project_id=project_id, status_filter=status_filter, year=year, month=month
        )
        today = date.today()
        rows = []
        for inv in invs:
            r = svc.invoice_to_read(inv, today)
            rows.append(
                {
                    "projeto": r.get("project_name") or "",
                    "numero_nf": r["numero_nf"],
                    "valor_bruto": float(r["valor_bruto"]),
                    "vencimento": r["vencimento"].isoformat()
                    if isinstance(r["vencimento"], date)
                    else str(r["vencimento"]),
                    "total_recebido": float(r["total_recebido"]),
                    "saldo": float(r["saldo"]),
                    "status": r["status"],
                }
            )
        return {
            "filters": {
                "project_id": str(project_id) if project_id else None,
                "status": status_filter,
                "year": year,
                "month": month,
            },
            "rows": rows,
        }

    async def generate_debt_report(self, *, competencia: str) -> dict[str, Any]:
        svc = CompanyFinanceService(self.session)
        items = await svc.list_items(tipo="endividamento", competencia=competencia)
        return {"tipo": "endividamento", "competencia": competencia, "items": items}

    async def generate_fixed_costs_report(self, *, competencia: str) -> dict[str, Any]:
        svc = CompanyFinanceService(self.session)
        items = await svc.list_items(tipo="custo_fixo", competencia=competencia)
        return {"tipo": "custo_fixo", "competencia": competencia, "items": items}

    async def generate_dashboard_report(
        self,
        *,
        competencia: date,
        project_id: UUID | None,
        months: int,
    ) -> dict[str, Any]:
        dash = DashboardService(self.session)
        if project_id is None:
            s = await dash.resumo_geral_diretor(competencia=competencia)
            series = await dash.serie_mensal(project_id=None, months=months)
        else:
            s = await dash.resumo_por_projeto(project_id=project_id, competencia=competencia)
            series = await dash.serie_mensal(project_id=project_id, months=months)
        summary = FinancialDashboardSummary(
            summary=DirectorSummary.model_validate(s),
            monthly_series=[MonthlyPoint.model_validate(x) for x in series],
        )
        return {
            "summary": summary.model_dump(mode="json"),
            "months": months,
            "project_id": str(project_id) if project_id else None,
        }

    async def generate_users_report(self) -> dict[str, Any]:
        users = await UsersService(self.session).list_users(offset=0, limit=10_000)
        rows: list[dict[str, Any]] = []
        for u in users:
            role_names = [
                link.role.name
                for link in (getattr(u, "roles", []) or [])
                if getattr(link, "role", None)
            ]
            rows.append(
                {
                    "email": u.email,
                    "nome": u.full_name,
                    "ativo": u.is_active,
                    "papeis": ", ".join(role_names),
                }
            )
        return {"rows": rows}

    async def generate_revenues_report(self, *, project_id: UUID | None) -> dict[str, Any]:
        rows = await FinancialCrudService(self.session).list_revenues(
            offset=0, limit=10_000, project_id=project_id
        )
        out: list[dict[str, Any]] = []
        for r in rows:
            comp = r.competencia
            out.append(
                {
                    "project_id": str(r.project_id),
                    "competencia": comp.isoformat() if isinstance(comp, date) else str(comp),
                    "valor": float(r.amount),
                    "descricao": r.description or "",
                    "status": r.status,
                    "retencao": bool(r.has_retention),
                }
            )
        return {"filters": {"project_id": str(project_id) if project_id else None}, "rows": out}


async def list_project_ids_for_user(session: AsyncSession, user: User) -> list[UUID]:
    from app.api.deps import ROLE_ADMIN, ROLE_CONSULTA, _user_role_names

    roles = _user_role_names(user)
    svc = ProjectsService(session)
    if ROLE_ADMIN in roles or ROLE_CONSULTA in roles:
        plist = await svc.list_projects(offset=0, limit=10_000)
    else:
        plist = await svc.list_projects_for_user(user_id=user.id, offset=0, limit=10_000)
    return [p.id for p in plist]
