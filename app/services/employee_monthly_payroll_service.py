from __future__ import annotations

import re
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.employee_monthly_payroll_override import EmployeeMonthlyPayrollOverride
from app.schemas.employee_monthly_payroll import EmployeeMonthlyPayrollRead, EmployeeMonthlyPayrollUpsert
from app.services.payable_snapshot_service import PayableSnapshotService

_COMPETENCE_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def normalize_competence_month(value: str) -> str:
    raw = (value or "").strip()
    if not _COMPETENCE_MONTH_RE.match(raw):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Competência inválida; use o formato YYYY-MM.",
        )
    return raw


class EmployeeMonthlyPayrollService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get_employee(self, employee_id: UUID) -> Employee:
        emp = await self.session.get(Employee, employee_id)
        if not emp:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Colaborador não encontrado.")
        return emp

    async def get(
        self, *, employee_id: UUID, competence_month: str
    ) -> EmployeeMonthlyPayrollOverride | None:
        comp = normalize_competence_month(competence_month)
        await self._get_employee(employee_id)
        return (
            await self.session.execute(
                select(EmployeeMonthlyPayrollOverride).where(
                    EmployeeMonthlyPayrollOverride.employee_id == employee_id,
                    EmployeeMonthlyPayrollOverride.competence_month == comp,
                )
            )
        ).scalar_one_or_none()

    async def upsert(
        self,
        *,
        employee_id: UUID,
        competence_month: str,
        payload: EmployeeMonthlyPayrollUpsert,
    ) -> EmployeeMonthlyPayrollRead:
        comp = normalize_competence_month(competence_month)
        emp = await self._get_employee(employee_id)
        if (emp.employment_type or "").strip().upper() != "CLT":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Folha real mensal aplica-se apenas a colaboradores CLT.",
            )

        row = await self.get(employee_id=employee_id, competence_month=comp)
        data = payload.model_dump()
        if row is None:
            row = EmployeeMonthlyPayrollOverride(
                employee_id=employee_id,
                competence_month=comp,
                **data,
            )
            self.session.add(row)
        else:
            row.net_salary_amount = data["net_salary_amount"]
            row.vr_amount = data["vr_amount"]
            row.notes = data["notes"]

        await self.session.flush()
        await PayableSnapshotService(self.session).sync_collaborator_payables_for_employee(
            employee_id=employee_id
        )
        await self.session.commit()
        await self.session.refresh(row)
        return EmployeeMonthlyPayrollRead.model_validate(row)
