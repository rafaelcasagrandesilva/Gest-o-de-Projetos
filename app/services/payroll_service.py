from __future__ import annotations

from collections import defaultdict
from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scenario import Scenario, coerce_scenario
from app.models.employee import Employee
from app.repositories.company_staff_cost import CompanyStaffCostRepository
from app.repositories.employees import EmployeeRepository
from app.repositories.project_operational import ProjectLaborRepository
from app.schemas.employees import (
    PayrollLineRead,
    PayrollProjectSlice,
    PayrollResponse,
    PayrollTotalsRead,
)
from app.services.employee_cost_service import project_labor_full_monthly_cost
from app.services.settings_service import SettingsService
from app.utils.date_utils import normalize_competencia


class PayrollService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.labors = ProjectLaborRepository(session)
        self.staff_costs = CompanyStaffCostRepository(session)
        self.employees = EmployeeRepository(session)

    def _line_for_employee(
        self,
        *,
        emp: Employee,
        pl_rows: list,
        admin: float,
        settings_row,
        competencia: date,
    ) -> PayrollLineRead:
        slices: list[PayrollProjectSlice] = []
        projects_total = 0.0
        for pl in pl_rows:
            if not pl.project:
                continue
            emp_obj = pl.employee or emp
            full = project_labor_full_monthly_cost(emp_obj, settings_row, competencia, pl)
            pct = float(pl.allocation_percentage)
            factor = pct / 100.0
            allocated = round(float(full) * factor, 2)
            projects_total += allocated
            slices.append(
                PayrollProjectSlice(
                    project_id=pl.project_id,
                    project_name=pl.project.name,
                    labor_id=pl.id,
                    allocation_percentage=pct,
                    full_monthly_cost=round(float(full), 2),
                    allocated_cost=allocated,
                )
            )
        admin_f = round(float(admin), 2)
        projects_total = round(projects_total, 2)
        grand = round(projects_total + admin_f, 2)
        return PayrollLineRead(
            employee_id=emp.id,
            full_name=emp.full_name,
            employment_type=emp.employment_type,
            role_title=emp.role_title,
            is_active=bool(emp.is_active),
            by_project=slices,
            projects_total=projects_total,
            administrative_cost=admin_f,
            grand_total=grand,
        )

    async def build_payroll(
        self,
        *,
        competencia: date,
        scenario: str | Scenario,
        project_id: UUID | None = None,
    ) -> PayrollResponse:
        comp = normalize_competencia(competencia)
        sc = coerce_scenario(scenario)
        settings_row = await SettingsService(self.session).get_or_create()

        labors = await self.labors.list_by_competencia(
            competencia=comp, scenario=sc, project_id=project_id
        )
        staff_rows = await self.staff_costs.list_by_competencia_scenario(
            competencia=comp, scenario=sc
        )

        by_emp_labors: dict[UUID, list] = defaultdict(list)
        for pl in labors:
            by_emp_labors[pl.employee_id].append(pl)

        admin_map: dict[UUID, float] = {}
        for row in staff_rows:
            admin_map[row.employee_id] = float(row.valor or 0)

        active_list = await self.employees.list_active_ordered()
        active_ids = {e.id for e in active_list}
        data_ids = set(by_emp_labors.keys()) | set(admin_map.keys())
        show_ids = active_ids | data_ids

        emp_by_id: dict[UUID, Employee] = {e.id: e for e in active_list}
        for eid in show_ids:
            if eid not in emp_by_id:
                e = await self.employees.get(eid)
                if e:
                    emp_by_id[eid] = e

        ordered = [emp_by_id[i] for i in show_ids if i in emp_by_id]
        ordered.sort(key=lambda e: (not e.is_active, e.full_name.lower()))

        lines: list[PayrollLineRead] = []
        sum_proj = 0.0
        sum_adm = 0.0
        for emp in ordered:
            pls = by_emp_labors.get(emp.id, [])
            adm = admin_map.get(emp.id, 0.0)
            line = self._line_for_employee(
                emp=emp,
                pl_rows=pls,
                admin=adm,
                settings_row=settings_row,
                competencia=comp,
            )
            lines.append(line)
            sum_proj += line.projects_total
            sum_adm += line.administrative_cost

        grand = round(sum_proj + sum_adm, 2)
        return PayrollResponse(
            competencia=comp,
            scenario=sc.value,
            project_id=project_id,
            lines=lines,
            totals=PayrollTotalsRead(
                sum_projects=round(sum_proj, 2),
                sum_administrative=round(sum_adm, 2),
                grand_total=grand,
            ),
        )
