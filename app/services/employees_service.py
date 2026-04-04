from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scenario import Scenario
from app.models.employee import Employee, EmployeeAllocation
from app.repositories.employees import EmployeeAllocationRepository, EmployeeRepository
from app.schemas.employees import EmployeeRead
from app.services.audit_service import AuditService
from app.services.employee_cost_service import calculate_clt_cost, calculate_pj_total_cost
from app.services.settings_service import SettingsService
from app.services.utils import model_to_dict


def default_cost_reference() -> date:
    return date.today().replace(day=1)


_EMPLOYEE_PATCHABLE = frozenset(
    {
        "full_name",
        "email",
        "role_title",
        "employment_type",
        "salary_base",
        "additional_costs",
        "is_active",
        "has_periculosidade",
        "has_adicional_dirigida",
        "extra_hours_50",
        "extra_hours_70",
        "extra_hours_100",
        "pj_hours_per_month",
        "pj_additional_cost",
    }
)


class EmployeesService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.employees = EmployeeRepository(session)
        self.allocations = EmployeeAllocationRepository(session)
        self.audit = AuditService(session)

    async def _compute_and_assign_total_cost(self, emp: Employee, *, reference: date | None) -> None:
        ref = reference or default_cost_reference()
        settings = await SettingsService(self.session).get_or_create()
        if emp.employment_type == "CLT":
            emp.total_cost = calculate_clt_cost(emp, settings, ref.year, ref.month)
        else:
            emp.total_cost = calculate_pj_total_cost(emp)

    async def employee_to_read(self, emp: Employee, *, competencia: date) -> EmployeeRead:
        settings = await SettingsService(self.session).get_or_create()
        if emp.employment_type == "CLT":
            tc = calculate_clt_cost(emp, settings, competencia.year, competencia.month)
        else:
            tc = calculate_pj_total_cost(emp)
        base = EmployeeRead.model_validate(emp)
        return base.model_copy(update={"total_cost": tc})

    async def list_employees_as_read(self, *, offset: int = 0, limit: int = 50, competencia: date) -> list[EmployeeRead]:
        rows = await self.employees.list(offset=offset, limit=limit)
        settings = await SettingsService(self.session).get_or_create()
        y, m = competencia.year, competencia.month
        out: list[EmployeeRead] = []
        for emp in rows:
            if emp.employment_type == "CLT":
                tc = calculate_clt_cost(emp, settings, y, m)
            else:
                tc = calculate_pj_total_cost(emp)
            out.append(EmployeeRead.model_validate(emp).model_copy(update={"total_cost": tc}))
        return out

    async def list_employees(self, *, offset: int = 0, limit: int = 50) -> list[Employee]:
        return await self.employees.list(offset=offset, limit=limit)

    async def get_employee(self, employee_id) -> Employee:
        emp = await self.employees.get(employee_id)
        if not emp:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Colaborador não encontrado.")
        return emp

    async def create_employee(self, *, actor_user_id, data: dict) -> Employee:
        payload = {**data}
        payload.pop("total_cost", None)
        ref = payload.pop("cost_reference_competencia", None)
        ref_date = ref if isinstance(ref, date) else default_cost_reference()

        employment_type = payload.get("employment_type") or "CLT"
        if employment_type == "CLT":
            sb = payload.get("salary_base")
            if sb is not None and float(sb) < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Salário base não pode ser negativo.",
                )

        emp = Employee(
            full_name=payload["full_name"],
            email=payload.get("email"),
            role_title=payload.get("role_title"),
            employment_type=employment_type,
            salary_base=payload.get("salary_base"),
            additional_costs=payload.get("additional_costs"),
            is_active=payload.get("is_active", True),
            has_periculosidade=bool(payload.get("has_periculosidade", False)),
            has_adicional_dirigida=bool(payload.get("has_adicional_dirigida", False)),
            extra_hours_50=float(payload.get("extra_hours_50") or 0),
            extra_hours_70=float(payload.get("extra_hours_70") or 0),
            extra_hours_100=float(payload.get("extra_hours_100") or 0),
            pj_hours_per_month=payload.get("pj_hours_per_month"),
            pj_additional_cost=float(payload.get("pj_additional_cost") or 0),
        )
        await self._compute_and_assign_total_cost(emp, reference=ref_date)
        await self.employees.add(emp)
        await self.audit.log(
            actor_user_id=actor_user_id,
            action="create",
            entity="Employee",
            entity_id=emp.id,
            before=None,
            after=model_to_dict(emp),
        )
        await self.session.commit()
        await self.session.refresh(emp)
        return emp

    async def update_employee(self, *, actor_user_id, employee_id, data: dict) -> Employee:
        emp = await self.get_employee(employee_id)
        before = model_to_dict(emp)
        data.pop("total_cost", None)
        ref = data.pop("cost_reference_competencia", None)
        ref_date = ref if isinstance(ref, date) else None
        patch = {k: v for k, v in data.items() if k in _EMPLOYEE_PATCHABLE}
        for k, v in patch.items():
            setattr(emp, k, v)

        if emp.employment_type == "CLT":
            sb = emp.salary_base
            if sb is not None and float(sb) < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Salário base não pode ser negativo.",
                )

        await self._compute_and_assign_total_cost(emp, reference=ref_date)
        await self.audit.log(
            actor_user_id=actor_user_id,
            action="update",
            entity="Employee",
            entity_id=emp.id,
            before=before,
            after=model_to_dict(emp),
        )
        await self.session.commit()
        await self.session.refresh(emp)
        return emp

    async def delete_employee(self, *, actor_user_id, employee_id) -> None:
        emp = await self.get_employee(employee_id)
        before = model_to_dict(emp)
        await self.employees.delete(emp)
        await self.audit.log(
            actor_user_id=actor_user_id,
            action="delete",
            entity="Employee",
            entity_id=employee_id,
            before=before,
            after=None,
        )
        await self.session.commit()

    async def list_allocations_by_project(
        self,
        *,
        project_id: UUID,
        scenario: str | Scenario | None = None,
        competencia: date | None = None,
    ) -> list[EmployeeAllocation]:
        return await self.allocations.list_by_project(
            project_id=project_id, scenario=scenario, competencia=competencia
        )

    async def create_allocation(self, *, actor_user_id, data: dict) -> EmployeeAllocation:
        alloc = EmployeeAllocation(**data)
        await self.allocations.add(alloc)
        await self.audit.log(
            actor_user_id=actor_user_id,
            action="create",
            entity="EmployeeAllocation",
            entity_id=alloc.id,
            before=None,
            after=model_to_dict(alloc),
        )
        await self.session.commit()
        await self.session.refresh(alloc)
        return alloc
